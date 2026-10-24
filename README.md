# Huawei HiLink Opple Light (cloud) — Home Assistant integration

Unofficial integration to control an **Opple Smart Desk Lamp** (Huawei HiLink) from
Home Assistant, via Huawei's cloud MQTT bridge (`smartlife-dre.things.dbankcloud.com`).

Personal reverse-engineering project: these lamps' local HiLink hub was abandoned by
Huawei, so the cloud path (Huawei account + MQTT) is the only one still working.

## ⚠️ Status

- Real-time control (on/off, brightness, color temperature): validated on a real lamp.
- Automatic token refresh (`refresh_token`): validated.
- Automatic credential retrieval (`account` + `devices`) via `get_credentials.py`
  (shipped inside the integration's own folder, its exact path is shown on the
  "Add integration" screen): validated.

Only use this integration if you're comfortable tinkering: it's a reverse-engineered,
undocumented private API with no guarantee from Huawei.

## Installing via HACS (custom repository)

1. In Home Assistant: **HACS → ⋮ (top-right menu) → Custom repositories**.
2. Paste this GitHub repo's URL, category **Integration**.
3. Search for "Huawei HiLink Opple Light (cloud)" in HACS and install it.
4. Restart Home Assistant.
5. **Settings → Devices & services → Add integration → Huawei HiLink (cloud)**.
6. Paste the configuration JSON (see below).

## Getting your credentials

Everything is automated by `get_credentials.py`, **shipped with the integration**
(installed by HACS at `<HA config dir>/custom_components/huawei_hilink_cloud/
get_credentials.py`) — the "Add integration" screen in Home Assistant shows this
exact path and what to do next, no need to go back to GitHub or know anything
about the reverse engineering involved.

1. Once, on a computer **with a browser** (not necessarily the one hosting Home
   Assistant — a headless NAS or Raspberry Pi has no display): install Playwright
   and its Chromium.

   ```bash
   pip install playwright
   playwright install chromium
   ```

2. Copy `get_credentials.py` from the integration's folder to that computer (Samba,
   SSH, the Terminal/File editor add-on...), then run it:

   ```bash
   python3 get_credentials.py
   ```

3. A **visible** Chromium window opens on the official `oauth-login1.cloud.huawei.com`
   page. Log in with your Huawei account and authorize access, just like in the
   official app.
4. The script automatically intercepts the `hms://redirect_url?code=...` redirect the
   moment the browser tries to open it (it can't handle that scheme, but the attempt is
   captured before it fails) — nothing to do on your end, no copy/pasting.
5. It then exchanges the code, resolves your account, and fetches your homes/devices on
   its own, and opens a local result page in your browser (`127.0.0.1` only) with a
   **Copy JSON** button. A `ha_credentials.json` backup file is also written to the
   current folder.
6. Paste that JSON into the Home Assistant configuration form — never anywhere else.

The script never prints `access_token`/`refresh_token`/`code` to the terminal — only a
summary (number of devices found, how long the token stays valid). If no device is
found, it also prints a short diagnostic (home count, which API call came back empty)
so the issue can be narrowed down; re-run with `--debug` for the full redacted output.

### Why not do this directly inside Home Assistant?

We considered it — but bundling a real browser engine (required to pass Huawei's
anti-bot checks) inside a HACS-installed integration would break for most users: an
integration can only install Python packages (`pip install`), never the system
libraries Chromium needs, and Home Assistant OS (the most common install) doesn't let
you add any. Hence the choice of a script shipped alongside the integration but run
separately, on a computer that has a real browser.

### Why a driven Chromium instead of a simple link to open?

The official Huawei app's `redirect_uri` (`hms://redirect_url`) is a custom URL scheme
that only the mobile app knows how to handle. On a PC, no manual copy/paste reliably
recovers that redirect (DevTools/network export works but stays fragile and hard to
reproduce). Driving a real browser and intercepting the navigation attempt at the
protocol level is the method used by the reference project
[`0xlic/ha-huawei-hilink-opple`](https://github.com/0xlic/ha-huawei-hilink-opple) — reused
here, adapted to keep `access_token`/`refresh_token` (needed for the cloud MQTT bridge,
unlike their local-control use case).

## License

MIT — see `LICENSE`. Not affiliated with Huawei or Opple.
