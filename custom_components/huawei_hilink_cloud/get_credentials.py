#!/usr/bin/env python3
"""Fully automated Huawei authorization flow - no copy/pasting a one-time code.

Opens a real, visible Chromium window (Playwright) on Huawei's official
authorization page. You log in normally. The script intercepts the
hms://redirect_url?code=... redirect at the moment it is attempted (the
browser can't open that custom scheme, but the navigation attempt itself is
captured before it fails) - no DevTools, no network export needed.

It then automatically chains:
  1. code -> access_token/refresh_token exchange (endpoint confirmed on
     2026-10-24: .../smart-life/v2/hms-lite/token)
  2. user_id resolution (.../smart-life/v2/hms-lite/userinfo)
  3. homes, then devices (.../userApp/v1.2.0/homes then
     .../smart-life/v2|v3/devices, host smarthome.hicloud.com - reused from
     the reference project 0xlic/ha-huawei-hilink-opple)

and opens a local, loopback-only web page with the resulting
{"account": ..., "devices": [...]} JSON ready to copy-paste into the Home
Assistant config flow for this integration - no file to hunt for and
re-open. A JSON file is still written alongside it as a backup.

access_token/refresh_token/code are NEVER printed to the terminal or
embedded anywhere but that local page, which only your own browser, on your
own machine, can reach.

This file lives INSIDE the integration's own folder (installed by HACS at
<HA config dir>/custom_components/huawei_hilink_cloud/get_credentials.py)
so it ships automatically with every install - no need to go hunting for it
elsewhere. The "Add integration" screen in Home Assistant shows this exact
path and what to do next.

Run this on a computer WITH A BROWSER (your PC/Mac), not necessarily the one
hosting Home Assistant if that one has no display (NAS, headless Raspberry
Pi, etc.) - just copy this one file to wherever you run it.

On startup it asks which country/region is selected in the Huawei AI Life app
(Me > Account > Country or Region) - this must match exactly, since it is
what routes the token exchange to the right Huawei data center (pass
--country-code to skip the prompt). The login page's own display language is
auto-detected from this machine's locale (override with --ui-locale).

One-time setup:
    pip install playwright
    playwright install chromium

Usage:
    python3 get_credentials.py [--output ha_credentials.json] [--timeout 180]
    python3 get_credentials.py --country-code uk   # skip the interactive prompt
    python3 get_credentials.py --debug   # also print redacted raw API responses
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import locale
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

BASE_URL = "https://smartlife-dre.things.dbankcloud.com"
AUTHORIZE_URL = "https://oauth-login1.cloud.huawei.com/oauth2/v3/authorize"
APP_ID = "10406921"
APP_VERSION = "17.0.3.320"
REDIRECT_URI = "hms://redirect_url"
TOKEN_URL = f"{BASE_URL}/smart-life/v2/hms-lite/token"
USERINFO_URL = f"{BASE_URL}/smart-life/v2/hms-lite/userinfo"
# Confirmed 2026-10-24: for an EU-region account, homes/devices must be
# fetched from the SAME regional host as the token exchange
# (smartlife-dre.things.dbankcloud.com), not the generic/global
# smarthome.hicloud.com the un-adapted reference project uses - the generic
# host silently returns zero devices for this account instead of erroring.
HOMES_URL = f"{BASE_URL}/userApp/v1.2.0/homes"
DEVICES_V2_URL = f"{BASE_URL}/smart-life/v2/devices"
DEVICES_V3_URL = f"{BASE_URL}/smart-life/v3/devices"
SCOPES = (
    "openid",
    "https://www.huawei.com/auth/account/base.profile",
    "https://smarthome.com/auth/smarthome/devices",
    "https://smarthome.com/auth/smarthome/skill",
)
# Keys that must never reach the terminal, the --debug dump, or anything
# else outside the local result page - even redacted/truncated.
SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "code",
    "authcode",
    "authCode",
    "password",
    "pwd",
    "ticket",
    "token",
}


# ---------------------------------------------------------------------------
# Step 1: build the authorization URL
# ---------------------------------------------------------------------------


def detect_ui_locale() -> str:
    """Best-effort "xx-xx" guess of this machine's own language/region (e.g.
    "fr-fr", "en-gb"), used only for the look of Huawei's login page - it has
    no effect on which data center handles the account (see countryCode)."""
    name: str | None = None
    try:
        # getdefaultlocale() is deprecated but, unlike getlocale(), it maps a
        # Windows locale name ("French_France") to the POSIX-style tag
        # ("fr_FR") we need - getlocale() alone would leave it unparsed there.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            name = locale.getdefaultlocale()[0]
    except Exception:
        name = None
    if not name:
        try:
            locale.setlocale(locale.LC_ALL, "")
            name = locale.getlocale()[0]
        except Exception:
            name = None
    if not name:
        name = os.environ.get("LANG") or os.environ.get("LC_ALL") or os.environ.get("LANGUAGE")
    if not name or name.upper() in {"C", "POSIX"}:
        return "en-us"
    name = name.split(".")[0].split(":")[0].replace("_", "-").lower()
    if "-" not in name:
        name = f"{name}-{name}"
    return name


def prompt_country_code(provided: str | None) -> str:
    """Ask which country/region is selected in the Huawei AI Life app.

    This is NOT cosmetic like the UI locale above: it is what Huawei's
    server uses to route the OAuth/token exchange to the right data center
    (confirmed on 2026-10-23 - the wrong value makes the token exchange or
    the homes/devices lookup silently come back empty)."""
    if provided:
        return _normalize_country_code(provided)
    print()
    print("Which country/region is selected in the Huawei AI Life app")
    print("(Me / Account > Country or Region)? Type the ISO code exactly as shown")
    print('there (e.g. GB, FR, DE) - it must match, or the token exchange can')
    print("silently fail or return zero devices.")
    raw = input("Country/region code: ").strip()
    while not raw:
        raw = input("Country/region code (required): ").strip()
    return _normalize_country_code(raw)


def _normalize_country_code(raw: str) -> str:
    code = raw.strip().upper()
    if code == "UK":
        # AI Life's own country picker labels this "UK", but Huawei's API
        # expects the ISO 3166-1 alpha-2 code, which is "GB".
        code = "GB"
    return code


def build_authorization_url(country_code: str, ui_locale: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    query = urllib.parse.urlencode(
        {
            "access_type": "offline",
            "response_type": "code",
            "client_id": APP_ID,
            "ui_locales": ui_locale,
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "scope": " ".join(SCOPES),
            "display": "touch",
            "nonce": nonce,
            "include_granted_scopes": "true",
            "uuid": str(uuid.uuid4()),
            "countryCode": country_code,
            "cVersion": "HwID_6.10.0.300",
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZE_URL}?{query}", state


def authorization_code_from_callback(value: str, expected_state: str) -> str:
    callback = urllib.parse.urlparse(value)
    if callback.scheme != "hms" or callback.netloc != "redirect_url":
        raise ValueError(f"unexpected callback: {callback.scheme}://{callback.netloc}")
    query = urllib.parse.parse_qs(callback.query)
    if query.get("state", [None])[0] != expected_state:
        raise ValueError("state does not match this attempt")
    code = query.get("code", [""])[0].strip()
    if not code:
        error = query.get("error_description", query.get("error", ["unknown reason"]))[0]
        raise ValueError(f"no code in callback (Huawei error: {error})")
    return code


# ---------------------------------------------------------------------------
# Step 2: capture the hms:// redirect with a driven Chromium
# ---------------------------------------------------------------------------


def capture_callback_with_playwright(authorization_url: str, *, timeout_seconds: int) -> str:
    """Open a visible Chromium and intercept the hms:// redirect the moment
    it is attempted, before the OS ever tries (and fails) to open it."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    callback_urls: list[str] = []

    def observe(url: str) -> None:
        if url.startswith("hms://redirect_url") and not callback_urls:
            callback_urls.append(url)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            # Several listening channels in parallel: any one of them is
            # enough to catch the navigation attempt, but not every browser
            # fires every event for a custom scheme.
            page.on("request", lambda request: observe(request.url))
            page.on("requestfailed", lambda request: observe(request.url))
            page.on("framenavigated", lambda frame: observe(frame.url))
            devtools = context.new_cdp_session(page)
            devtools.send("Page.enable")
            devtools.send("Network.enable")
            devtools.on(
                "Page.frameRequestedNavigation",
                lambda event: observe(str(event.get("url", ""))),
            )
            devtools.on(
                "Network.requestWillBeSent",
                lambda event: observe(str(event.get("request", {}).get("url", ""))),
            )
            try:
                page.goto(authorization_url, wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightError:
                if not callback_urls:
                    raise
            print("Chromium window opened - log in with your Huawei account and authorize access.")
            print("(The code will be captured automatically once you're done.)")
            deadline = time.monotonic() + timeout_seconds
            while not callback_urls and time.monotonic() < deadline:
                try:
                    page.wait_for_timeout(250)
                except PlaywrightError:
                    if callback_urls:
                        break
                    raise
            if not callback_urls:
                raise TimeoutError("Timed out without capturing the redirect - run the script again.")
            return callback_urls[0]
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Step 3: code -> tokens, then userinfo / homes / devices
# ---------------------------------------------------------------------------


# Best-effort country -> "x-language" header mapping. The reference app
# sends a BCP-47-ish tag that matches the ACCOUNT's own configured language,
# not a fixed "zh-CN" - on 2026-10-23 forcing this to the account's real
# region (then "en-GB") was what made the homes/devices lookup return
# results, after countryCode alone wasn't enough. Extend this table as more
# regions are confirmed; unknown codes fall back to "en-<COUNTRY>".
LANGUAGE_BY_COUNTRY = {
    "CN": "zh-CN",
    "GB": "en-GB",
    "US": "en-US",
    "FR": "fr-FR",
    "DE": "de-DE",
    "ES": "es-ES",
    "IT": "it-IT",
    "NL": "nl-NL",
    "BE": "fr-BE",
    "LU": "fr-LU",
    "PT": "pt-PT",
    "IE": "en-IE",
    "CH": "de-CH",
}


def _language_header(country_code: str) -> str:
    return LANGUAGE_BY_COUNTRY.get(country_code.upper(), f"en-{country_code.upper()}")


def _headers(
    access_token: str | None = None,
    extra: dict[str, str] | None = None,
    *,
    language: str = "zh-CN",
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": f"HuaweiSmartHome/{APP_VERSION}",
        "x-appId": APP_ID,
        "x-appVersion": APP_VERSION,
        "x-language": language,
        "x-ori-app-name": "com.huawei.smarthome",
        "x-phoneOs": "Android",
        "x-requestId": str(uuid.uuid4()),
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if extra:
        headers.update(extra)
    return headers


def _call(
    method: str,
    url: str,
    *,
    body: Any = None,
    access_token: str | None = None,
    extra_headers: dict[str, str] | None = None,
    language: str = "zh-CN",
) -> Any:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = urllib.request.Request(
        url, data=data, headers=_headers(access_token, extra_headers, language=language), method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} on {url}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"network error on {url}: {exc}") from None
    return json.loads(raw.decode())


def _redact(value: Any) -> Any:
    """Deep-copy a response while masking anything that looks like a secret,
    so it is safe to print for troubleshooting."""
    if isinstance(value, dict):
        redacted = {}
        for key, val in value.items():
            if key.lower() in {k.lower() for k in SENSITIVE_KEYS}:
                redacted[key] = "***redacted***"
            else:
                redacted[key] = _redact(val)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _walk(value: Any):
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                yield from _walk(json.loads(text))
            except json.JSONDecodeError:
                pass
        return
    yield value
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)


def _collect_values(value: Any, keys: set[str]) -> list[str]:
    found: list[str] = []
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        for key in keys:
            candidate = item.get(key)
            if isinstance(candidate, (str, int)) and str(candidate).strip():
                found.append(str(candidate).strip())
    return list(dict.fromkeys(found))


def _collect_device_records(value: Any) -> list[dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        device_id = next(
            (str(item[k]).strip() for k in ("devId", "deviceId", "deviceID") if item.get(k)),
            "",
        )
        if not device_id:
            continue
        record = records.setdefault(device_id, {"device_id": device_id})
        for src, dst in (
            ("productId", "model"),
            ("prodId", "model"),
            ("model", "model"),
            ("deviceName", "name"),
            ("name", "name"),
        ):
            candidate = item.get(src)
            if dst not in record and isinstance(candidate, (str, int)):
                record[dst] = str(candidate)
    return list(records.values())


def fetch_credentials(one_time_code: str, *, debug: bool, country_code: str) -> dict[str, Any]:
    language = _language_header(country_code)
    token_response = _call(
        "POST",
        TOKEN_URL,
        body={"appId": APP_ID, "code": urllib.parse.quote(one_time_code, safe="")},
        language=language,
    )
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = float(token_response.get("expires_in", 3600))
    if not access_token or not refresh_token:
        raise RuntimeError("incomplete token response")

    userinfo = _call(
        "POST", USERINFO_URL, body={"access_token": access_token}, access_token=access_token, language=language
    )
    user_id = userinfo.get("userId") or userinfo.get("openId")
    if not user_id:
        ids = _collect_values(userinfo, {"userId", "openId"})
        user_id = ids[0] if ids else None
    if not user_id:
        raise RuntimeError("no userId in the userinfo response")

    homes_response = _call("GET", HOMES_URL, access_token=access_token, language=language)
    home_ids = _collect_values(homes_response, {"homeId"})

    diagnostics: list[str] = [f"x-language used: {language}", f"homes: {len(home_ids)} found -> {home_ids}"]
    if debug:
        diagnostics.append("raw homes response: " + json.dumps(_redact(homes_response), ensure_ascii=False))

    all_devices: list[dict[str, str]] = []
    for home_id in home_ids:
        response = _call(
            "GET",
            DEVICES_V2_URL,
            access_token=access_token,
            extra_headers={"x-homeId": home_id},
            language=language,
        )
        found = _collect_device_records(response)
        diagnostics.append(f"devices v2 for home {home_id}: {len(found)} found")
        if debug:
            diagnostics.append("raw devices v2 response: " + json.dumps(_redact(response), ensure_ascii=False))
        all_devices.extend(found)
    if home_ids:
        query = urllib.parse.urlencode({"homeId": ",".join(home_ids)})
        response = _call("GET", f"{DEVICES_V3_URL}?{query}", access_token=access_token, language=language)
        found = _collect_device_records(response)
        diagnostics.append(f"devices v3 (all homes): {len(found)} found")
        if debug:
            diagnostics.append("raw devices v3 response: " + json.dumps(_redact(response), ensure_ascii=False))
        all_devices.extend(found)

    devices_by_id: dict[str, dict[str, str]] = {}
    for record in all_devices:
        current = devices_by_id.setdefault(record["device_id"], {"device_id": record["device_id"]})
        current.update(record)

    if not home_ids:
        diagnostics.append(
            "No home was returned for this account - the account the browser logged into may not "
            "match the one your lamps are paired to, or it may not be registered in this region yet."
        )
    elif not devices_by_id:
        diagnostics.append(
            "Home(s) found but no device inside them - the lamps may be paired to a different home, "
            "or not currently online in the Huawei app. Re-run with --debug and share the (redacted) "
            "output."
        )

    return {
        "account": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_id,
            "expires_at": time.time() + expires_in,
        },
        "devices": list(devices_by_id.values()),
        "_home_count": len(home_ids),
        "_expires_in": expires_in,
        "_diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# Step 4: show the result on a local, loopback-only page with a copy button
# ---------------------------------------------------------------------------

RESULT_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Huawei HiLink credentials</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 860px; margin: 48px auto; padding: 0 20px; line-height: 1.55; }}
    .card {{ border: 1px solid #8886; border-radius: 14px; padding: 20px; margin: 18px 0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border-bottom: 1px solid #8885; padding: 9px; text-align: left; }}
    button {{ padding: 10px 16px; cursor: pointer; font-size: 1rem; }}
    textarea {{ width: 100%; height: 220px; font-family: ui-monospace, monospace; font-size: .85rem; }}
    code {{ overflow-wrap: anywhere; }}
    .muted {{ opacity: .72; }}
    .warn {{ color: #c77b00; }}
    #copied {{ color: #2a8a3e; font-weight: 600; display: none; }}
  </style>
</head>
<body>
  <h1>Huawei HiLink (cloud) credentials</h1>
  <p class="muted">Served only on <code>127.0.0.1</code> for this one run. Nothing on this page
    ever leaves your machine.</p>
  <div class="card">
    <p>{summary_html}</p>
    <h2>Devices found ({device_count})</h2>
    {device_table_html}
    <button id="copy">Copy JSON for Home Assistant</button>
    <span id="copied">Copied!</span>
    <p class="muted">Paste this into the "Add integration" form for Huawei HiLink Opple Light (cloud).</p>
    <textarea id="payload" readonly>{json_text}</textarea>
  </div>
  {diagnostics_html}
  <p class="muted">A copy was also written to <code>{output_path}</code> as a backup.
    Close this tab and press Ctrl-C in the terminal when you're done - the server stops
    automatically after {timeout_minutes} minutes either way.</p>
  <script>
    document.querySelector('#copy').addEventListener('click', async () => {{
      const text = document.querySelector('#payload').value;
      try {{
        await navigator.clipboard.writeText(text);
      }} catch (err) {{
        document.querySelector('#payload').select();
        document.execCommand('copy');
      }}
      const copied = document.querySelector('#copied');
      copied.style.display = 'inline';
      setTimeout(() => {{ copied.style.display = 'none'; }}, 2000);
    }});
  </script>
</body>
</html>
"""


def _build_result_page(result: dict[str, Any], *, output_path: str, server_timeout_minutes: int) -> str:
    devices = result["devices"]
    json_text = json.dumps({"account": result["account"], "devices": devices}, ensure_ascii=False, indent=2)
    if devices:
        summary_html = f"Found {len(devices)} device(s) across {result['_home_count']} home(s)."
        rows = "".join(
            f"<tr><td>{d.get('name', '(unnamed)')}</td><td>{d.get('model', 'unknown')}</td>"
            f"<td><code>{d['device_id']}</code></td></tr>"
            for d in devices
        )
        device_table_html = (
            "<table><thead><tr><th>Name</th><th>Model</th><th>device_id</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        summary_html = (
            f'<span class="warn">No device was found ({result["_home_count"]} home(s) seen) - '
            "see diagnostics below.</span>"
        )
        device_table_html = ""
    diagnostics_html = ""
    if result.get("_diagnostics"):
        items = "".join(f"<li><code>{line}</code></li>" for line in result["_diagnostics"])
        diagnostics_html = f'<div class="card"><h2>Diagnostics</h2><ul>{items}</ul></div>'
    return RESULT_PAGE.format(
        summary_html=summary_html,
        device_count=len(devices),
        device_table_html=device_table_html,
        json_text=json_text,
        output_path=output_path,
        timeout_minutes=server_timeout_minutes,
        diagnostics_html=diagnostics_html,
    )


def serve_result_page(result: dict[str, Any], *, output_path: str, timeout_minutes: int = 10) -> None:
    """Serve the result once on a random loopback port/path, open it in the
    default browser, and shut down automatically after a short timeout."""
    page = _build_result_page(result, output_path=output_path, server_timeout_minutes=timeout_minutes).encode()
    route_secret = secrets.token_urlsafe(24)
    prefix = f"/{route_secret}"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:
            if urllib.parse.urlparse(self.path).path != prefix:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html;charset=UTF-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}{prefix}"
    print(f"Opening result page: {url}")
    webbrowser.open(url)

    timer = threading.Timer(timeout_minutes * 60, server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        timer.cancel()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="ha_credentials.json")
    parser.add_argument("--timeout", type=int, default=180, help="seconds allowed to log in (default 180)")
    parser.add_argument(
        "--server-timeout", type=int, default=10, help="minutes the local result page stays up (default 10)"
    )
    parser.add_argument(
        "--country-code",
        default=None,
        help=(
            "country/region selected in the Huawei AI Life app (e.g. uk, fr, de) - "
            "skips the interactive prompt"
        ),
    )
    parser.add_argument(
        "--ui-locale",
        default=None,
        help="login page language as xx-xx (e.g. fr-fr) - default: auto-detected from this machine",
    )
    parser.add_argument(
        "--debug", action="store_true", help="also print redacted raw API responses, for troubleshooting"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="skip the local result page, only write the JSON file"
    )
    args = parser.parse_args()

    country_code = prompt_country_code(args.country_code)
    ui_locale = args.ui_locale or detect_ui_locale()
    print(f"Using country/region: {country_code} - login page language: {ui_locale}")

    authorization_url, expected_state = build_authorization_url(country_code, ui_locale)
    callback_url = capture_callback_with_playwright(authorization_url, timeout_seconds=args.timeout)
    one_time_code = authorization_code_from_callback(callback_url, expected_state)

    print("Code captured, finishing the exchange...")
    result = fetch_credentials(one_time_code, debug=args.debug, country_code=country_code)
    home_count = result.pop("_home_count")
    expires_in = result.pop("_expires_in")
    diagnostics = result.pop("_diagnostics")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"account": result["account"], "devices": result["devices"]}, f, ensure_ascii=False, indent=2)

    print(f"OK - {home_count} home(s), {len(result['devices'])} device(s) found.")
    print(f"Token still valid for ~{int(expires_in // 60)} minutes.")
    print(f"Backup file written: {args.output}")
    for line in diagnostics:
        print(f"  - {line}")

    result["_home_count"] = home_count
    result["_diagnostics"] = diagnostics
    if args.no_browser:
        print("Paste the CONTENT of that file into the Home Assistant configuration form.")
    else:
        serve_result_page(result, output_path=args.output, timeout_minutes=args.server_timeout)


if __name__ == "__main__":
    main()
