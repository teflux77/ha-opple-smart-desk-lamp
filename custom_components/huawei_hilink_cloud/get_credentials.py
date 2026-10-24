#!/usr/bin/env python3
"""Flow d'autorisation Huawei entièrement automatisé, sans copier-coller.

Ouvre un vrai Chromium visible (Playwright) sur la page d'autorisation
officielle Huawei. Tu te connectes normalement. Le script intercepte la
redirection hms://redirect_url?code=... au moment où elle se produit (le
navigateur ne sait pas l'ouvrir, mais la tentative de navigation est
capturée avant d'échouer), sans jamais passer par les DevTools ou un
export de trace.

Il enchaîne ensuite automatiquement :
  1. échange code -> access_token/refresh_token (endpoint confirmé le
     2026-10-24 : .../smart-life/v2/hms-lite/token)
  2. résolution du user_id (.../smart-life/v2/hms-lite/userinfo)
  3. liste des maisons puis des appareils (.../userApp/v1.2.0/homes puis
     .../smart-life/v2|v3/devices, hôte smarthome.hicloud.com - repris du
     dépôt de référence 0xlic/ha-huawei-hilink-opple)

et écrit directement le JSON {"account": ..., "devices": [...]} attendu
par l'assistant de configuration Home Assistant de cette intégration.

N'affiche jamais access_token/refresh_token/code à l'écran - seulement un
résumé (nombre de maisons/appareils trouvés, durée de validité du token).

Ce fichier vit À L'INTÉRIEUR du dossier de l'intégration (installé par HACS
dans <config HA>/custom_components/huawei_hilink_cloud/get_credentials.py)
pour être livré automatiquement à chaque installation - inutile d'aller le
chercher ailleurs. L'écran "Ajouter l'intégration" dans Home Assistant
affiche son chemin exact et la marche à suivre.

À exécuter sur un ordinateur AVEC UN NAVIGATEUR (ton PC/Mac), pas forcément
celui qui héberge Home Assistant si celui-ci n'a pas d'écran (NAS,
Raspberry Pi en headless, etc.) - copie juste ce fichier là où tu l'exécutes.

Prérequis (une seule fois) :
    pip install playwright
    playwright install chromium

Usage :
    python3 get_credentials.py [--output ha_credentials.json] [--timeout 180]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

BASE_URL = "https://smartlife-dre.things.dbankcloud.com"
AUTHORIZE_URL = "https://oauth-login1.cloud.huawei.com/oauth2/v3/authorize"
APP_ID = "10406921"
APP_VERSION = "17.0.3.320"
REDIRECT_URI = "hms://redirect_url"
TOKEN_URL = f"{BASE_URL}/smart-life/v2/hms-lite/token"
USERINFO_URL = f"{BASE_URL}/smart-life/v2/hms-lite/userinfo"
HICLOUD_BASE = "https://smarthome.hicloud.com"
HOMES_URL = f"{HICLOUD_BASE}/userApp/v1.2.0/homes"
DEVICES_V2_URL = f"{HICLOUD_BASE}/smart-life/v2/devices"
DEVICES_V3_URL = f"{HICLOUD_BASE}/smart-life/v3/devices"
SCOPES = (
    "openid",
    "https://www.huawei.com/auth/account/base.profile",
    "https://smarthome.com/auth/smarthome/devices",
    "https://smarthome.com/auth/smarthome/skill",
)


# ---------------------------------------------------------------------------
# Étape 1 : construire l'URL d'autorisation
# ---------------------------------------------------------------------------


def build_authorization_url() -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    query = urllib.parse.urlencode(
        {
            "access_type": "offline",
            "response_type": "code",
            "client_id": APP_ID,
            "ui_locales": "zh-cn",
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "scope": " ".join(SCOPES),
            "display": "touch",
            "nonce": nonce,
            "include_granted_scopes": "true",
            "uuid": str(uuid.uuid4()),
            "countryCode": "GB",
            "cVersion": "HwID_6.10.0.300",
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZE_URL}?{query}", state


def authorization_code_from_callback(value: str, expected_state: str) -> str:
    callback = urllib.parse.urlparse(value)
    if callback.scheme != "hms" or callback.netloc != "redirect_url":
        raise ValueError(f"callback inattendu: {callback.scheme}://{callback.netloc}")
    query = urllib.parse.parse_qs(callback.query)
    if query.get("state", [None])[0] != expected_state:
        raise ValueError("state ne correspond pas à cette tentative")
    code = query.get("code", [""])[0].strip()
    if not code:
        error = query.get("error_description", query.get("error", ["raison inconnue"]))[0]
        raise ValueError(f"pas de code dans le callback (erreur Huawei: {error})")
    return code


# ---------------------------------------------------------------------------
# Étape 2 : capturer la redirection hms:// avec un Chromium piloté
# ---------------------------------------------------------------------------


def capture_callback_with_playwright(authorization_url: str, *, timeout_seconds: int) -> str:
    """Ouvre un Chromium visible et intercepte la redirection hms:// dès
    qu'elle est tentée, sans jamais laisser l'OS essayer de l'ouvrir."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright n'est pas installé. Lance : pip install playwright && playwright install chromium"
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
            # Plusieurs canaux d'écoute en parallèle : un seul suffit à
            # capturer la tentative de navigation, mais certains navigateurs
            # ne déclenchent pas tous les évènements pour un schéma custom.
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
            print("Fenêtre Chromium ouverte - connecte-toi avec ton compte Huawei et autorise l'accès.")
            print("(Le code sera capturé automatiquement dès la fin de la connexion.)")
            deadline = time.monotonic() + timeout_seconds
            while not callback_urls and time.monotonic() < deadline:
                try:
                    page.wait_for_timeout(250)
                except PlaywrightError:
                    if callback_urls:
                        break
                    raise
            if not callback_urls:
                raise TimeoutError("Temps écoulé sans capturer la redirection - relance le script.")
            return callback_urls[0]
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Étape 3 : échange code -> tokens, puis userinfo / homes / devices
# ---------------------------------------------------------------------------


def _headers(access_token: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": f"HuaweiSmartHome/{APP_VERSION}",
        "x-appId": APP_ID,
        "x-appVersion": APP_VERSION,
        "x-language": "zh-CN",
        "x-ori-app-name": "com.huawei.smarthome",
        "x-phoneOs": "Android",
        "x-requestId": str(uuid.uuid4()),
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if extra:
        headers.update(extra)
    return headers


def _call(method: str, url: str, *, body: Any = None, access_token: str | None = None, extra_headers: dict[str, str] | None = None) -> Any:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=data, headers=_headers(access_token, extra_headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} sur {url}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"erreur réseau sur {url}: {exc}") from None
    return json.loads(raw.decode())


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


def fetch_credentials(one_time_code: str) -> dict[str, Any]:
    token_response = _call("POST", TOKEN_URL, body={"appId": APP_ID, "code": urllib.parse.quote(one_time_code, safe="")})
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = float(token_response.get("expires_in", 3600))
    if not access_token or not refresh_token:
        raise RuntimeError("réponse token incomplète")

    userinfo = _call("POST", USERINFO_URL, body={"access_token": access_token}, access_token=access_token)
    user_id = userinfo.get("userId") or userinfo.get("openId")
    if not user_id:
        ids = _collect_values(userinfo, {"userId", "openId"})
        user_id = ids[0] if ids else None
    if not user_id:
        raise RuntimeError("userId introuvable dans la réponse userinfo")

    homes_response = _call("GET", HOMES_URL, access_token=access_token)
    home_ids = _collect_values(homes_response, {"homeId"})

    all_devices: list[dict[str, str]] = []
    for home_id in home_ids:
        response = _call("GET", DEVICES_V2_URL, access_token=access_token, extra_headers={"x-homeId": home_id})
        all_devices.extend(_collect_device_records(response))
    if home_ids:
        query = urllib.parse.urlencode({"homeId": ",".join(home_ids)})
        response = _call("GET", f"{DEVICES_V3_URL}?{query}", access_token=access_token)
        all_devices.extend(_collect_device_records(response))

    devices_by_id: dict[str, dict[str, str]] = {}
    for record in all_devices:
        current = devices_by_id.setdefault(record["device_id"], {"device_id": record["device_id"]})
        current.update(record)

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
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="ha_credentials.json")
    parser.add_argument("--timeout", type=int, default=180, help="secondes laissées pour te connecter (défaut 180)")
    args = parser.parse_args()

    authorization_url, expected_state = build_authorization_url()
    callback_url = capture_callback_with_playwright(authorization_url, timeout_seconds=args.timeout)
    one_time_code = authorization_code_from_callback(callback_url, expected_state)

    print("Code capturé, finalisation de l'échange...")
    result = fetch_credentials(one_time_code)
    home_count = result.pop("_home_count")
    expires_in = result.pop("_expires_in")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"OK - {home_count} maison(s), {len(result['devices'])} appareil(s) trouvé(s).")
    print(f"Token valide encore ~{int(expires_in // 60)} minutes.")
    print(f"Fichier écrit : {args.output}")
    print("Colle le CONTENU de ce fichier dans le formulaire de configuration de Home Assistant.")


if __name__ == "__main__":
    main()
