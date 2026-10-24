# Huawei HiLink Opple Light (cloud) — project context

Unofficial Home Assistant integration to control an **Opple Smart Desk Lamp** desk
lamp via Huawei's cloud MQTT bridge (these lamps' local HiLink hub was abandoned by
Huawei; only the cloud path via Huawei account + MQTT still works). Reverse-engineered
from the official **Huawei AI Life / Smart Life 17.0.3.320** Android app (APK
decompiled with jadx, traffic captured via PCAPdroid + DevTools HAR export).

Public GitHub repo: `teflux77/ha-opple-smart-desk-lamp`.

Working language: English (code comments, UI strings, docs). This file and the repo
are kept in English; only `translations/fr.json` stays French as a secondary locale.

## Current status (2026-10-24)

- ✅ Real-time control (on/off, brightness, color temperature) validated on a real lamp
  via MQTT.
- ✅ Automatic token refresh (`refresh_token`) validated.
- ✅ Automatic credential retrieval (`tools/auto_authorize.py`,
  Playwright) validated: captures the OAuth code without manual copy/paste, chains
  token → userinfo → homes → devices, writes the JSON ready for HA.
- ✅ Decision made (2026-10-24): the credential script (renamed
  `get_credentials.py`) lives **inside**
  `custom_components/huawei_hilink_cloud/` so HACS ships it automatically. The
  "Add integration" screen (`config_flow.py` + `strings.json`/`translations/`) shows
  the exact path and what to do — nobody needs to go back to GitHub or know anything
  about the reverse engineering. The "everything inside HA, zero external script"
  alternative was explicitly ruled out: bundling a browser engine inside a
  HACS-installed integration would break on Home Assistant OS (no installable system
  libraries). See the README's "Why not do this directly inside Home Assistant?"
  section for the full explanation.
- ✅ `get_credentials.py` now opens a local, loopback-only ("127.0.0.1") result page
  with a "Copy JSON" button (mirroring the reference project's `credential_web.py`
  workflow) instead of only writing a file — a JSON file is still written as a backup.
- ✅ `config_flow.py` no longer rejects a pasted JSON as "invalid" just because
  `devices` came back empty — that was a real bug: valid JSON with zero devices was
  reported as a parsing error. It now creates the entry with zero light entities and
  logs a warning instead, so setup isn't blocked while debugging device discovery.
- ⚠️ Open issue (2026-10-24, live test by Stéphane): `get_credentials.py` ran
  successfully (token exchange worked, pasted JSON was syntactically valid) but
  returned `"devices": []`. Not yet root-caused. `get_credentials.py` now prints
  non-sensitive diagnostics (home count/ids, per-endpoint device counts, `--debug` for
  full redacted raw responses) specifically to narrow this down on the next run. Likely
  suspects, not yet confirmed: the homes/devices host
  (`https://smarthome.hicloud.com`, generic/global — confirmed correct by APK
  decompilation, unlike the token-exchange host which genuinely is
  region-specific) might still need a region-aware variant for this account's data
  residency; or the account that logged in in the browser didn't match the one the
  lamps are paired to.
- ⏳ Not yet tested end-to-end in a full HA install (fresh install + adding the
  integration from scratch, with the new screen text).
- 💭 Discussed but not done: extract the auth logic (token exchange, refresh,
  homes/devices) into a separate `huawei_cloud_auth/` module reusable by future
  integrations for other Huawei cloud devices (not just Opple lamps).

## Architecture

```
custom_components/huawei_hilink_cloud/
  __init__.py       entry setup/unload, instantiates HuaweiCloudMqttClient
  cloud_client.py    framework-agnostic core: OAuth token refresh,
                      persistent MQTT/TLS connection, sending commands,
                      dispatching notify messages (ACK + deviceDataChanged)
  config_flow.py     single-step "paste the JSON" flow (no native HA OAuth -
                      see "Why not native HA OAuth" below)
  const.py           domain constants, MQTT services (switch/brightness/cct/...)
  light.py           HA light entity, pushed in real time (should_poll=False)
  get_credentials.py LOCAL script (user's PC, not run inside HA): captures the
                      OAuth code via a driven Chromium (Playwright) and opens a
                      local result page with the {"account": {...}, "devices": [...]}
                      JSON to paste into the HA configuration form
  manifest.json
```

## Confirmed Huawei endpoints (APK reverse engineering, 2026-10-24)

All on `https://smartlife-dre.things.dbankcloud.com` unless noted otherwise.
Required headers on EVERY call below (a call missing these headers is rejected
before the body is even validated):

```
Accept: application/json
Content-Type: application/json;charset=UTF-8
User-Agent: HuaweiSmartHome/17.0.3.320
x-appId: 10406921
x-appVersion: 17.0.3.320
x-language: zh-CN
x-ori-app-name: com.huawei.smarthome
x-phoneOs: Android
x-requestId: <fresh uuid per call>
```

- `POST /smart-life/v2/hms-lite/token` — code→tokens exchange.
  Body: `{"appId": APP_ID, "code": urllib.parse.quote(one_time_code)}`
  (the code IS url-encoded before being put into the JSON — confirmed by
  decompilation, not a typo).
- `POST /smart-life/v2/hms-lite/refreshToken` — a **different** endpoint from
  `/token`, not a `grant_type` on the same path (trap: the first intuition of
  "same URL + grantType=refresh_token" silently fails with a generic
  `"System error"`).
  Body: `{"appId": APP_ID, "refresh_token": <raw, NOT url-encoded>}`.
  Source: `RefreshTokenEntity` class (`@JSONField(name="refresh_token")`)
  + `mk1.refreshAccessToken()` in the decompiled APK.
- `POST /smart-life/v2/hms-lite/userinfo` — body `{"access_token": ...}`,
  also with `Authorization: Bearer <access_token>`. Response contains `userId`.
- `GET https://smarthome.hicloud.com/userApp/v1.2.0/homes` — list of homes
  (`Authorization: Bearer <access_token>`). Note: **different** host
  (`smarthome.hicloud.com`, not `smartlife-dre.things.dbankcloud.com`).
- `GET https://smarthome.hicloud.com/smart-life/v2/devices` — with header
  `x-homeId: <homeId>`.
- `GET https://smarthome.hicloud.com/smart-life/v3/devices?homeId=<comma,separated,ids>`

MQTT (confirmed, real lamp):
- broker `smartlife-dre.things.dbankcloud.com:8883`, TLS without chain
  verification (the cert is only validated via pinning on the official app's
  side, not a public CA).
- command topic: `/smartHome/signaltrans/v2/categories/command`
- notify topic: `smarthome.notify.app.v1`
- envelope: `{"header": {method, accessToken, mode, requestId, from, to,
  timestamp}, "body": {...}}`

## Why not native HA OAuth (`config_entry_oauth2_flow`)

A discovered constraint, not a convenience choice: the official Huawei app's
`redirect_uri` (whose `client_id` we reuse, extracted from the APK,
`10406921`) is hardcoded to `hms://redirect_url` — a custom URL scheme no
desktop browser knows how to open. It can't be swapped for HA's own callback
URL (`my.home-assistant.io/redirect/...`) the way Spotify/Google integrations
do, because Huawei validates `redirect_uri` against whatever is registered for
that `client_id` server-side. On top of that, their CAS login page runs
anti-bot checks (ticket verification, `trustBrowser`/`chkRisk` browser
fingerprinting) that block any automated HTTP request without a real
JS-rendering engine.

Consequence: a real browser (even a Playwright-driven one) is **necessary** to
pass these checks, not a shortcut. And running it *from HA itself* would only
work if HA ran on the machine the user is sitting at — in most installs
(Raspberry Pi, NAS, dedicated VM), HA has no screen. Hence the choice of a
separate local script (`get_credentials.py`), run once on the user's own
computer, that produces JSON to paste into the HA form.

## Possible next steps

1. Root-cause the empty `devices: []` result (see "Open issue" above): re-run
   `get_credentials.py --debug` and inspect the redacted homes/devices
   responses; confirm whether the logged-in account actually owns the paired
   lamps; check whether the generic `smarthome.hicloud.com` host genuinely
   serves this account's region or needs a `-dre`-style regional variant.
2. End-to-end test in a real HA install (adding the integration via the JSON
   produced by `get_credentials.py`, verifying the refreshed `refresh_token`
   persists in the config_entry across an HA restart).
3. Decide whether to extract the auth logic into a shared
   `huawei_cloud_auth/` module (generalizing to other Huawei cloud devices
   beyond Opple lamps) — discussed, not yet done.
4. Decide on the distribution channel: HACS (public repo, already the case)
   vs. manually copying `custom_components/huawei_hilink_cloud/` into the HA
   install — no confidentiality constraint, the repo is already public.

## Precautions

Never display or commit `access_token`, `refresh_token`, or a plaintext OAuth
authorization code (not in code, not in messages, not in versioned debug
files). `get_credentials.py` only writes the final result JSON locally and to
its own loopback-only result page — never to the console.
