"""Config flow for the Huawei HiLink cloud (MQTT) integration.

Setup is a single paste step. The user runs get_credentials.py - shipped
INSIDE this integration's own folder, so HACS installs it automatically -
on any computer with a browser (not necessarily the one hosting Home
Assistant, which often has no display). That script drives a real Chromium
(Playwright) through the Huawei login, which is required to pass Huawei's
anti-bot checks (a plain HTTP request without a real browser gets rejected
- see CLAUDE.md for the reverse-engineering notes), then opens a local
result page (127.0.0.1 only) with a "Copy JSON" button combining the
account tokens and the device list - nothing is typed by hand and no OAuth
dance happens inside Home Assistant's own process. This is a deliberate
choice, not a stopgap: embedding a full browser engine inside a
HACS-installed integration would require system libraries that can't be
installed on Home Assistant OS, so it would break for most real installs.

Expected JSON shape::

    {
      "account": {
        "access_token": "...",
        "refresh_token": "...",
        "user_id": "...",
        "expires_at": 1761310000.0
      },
      "devices": [
        {"device_id": "...", "name": "Bureau", "model": "Opple H002"}
      ]
    }
"""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HuaweiHilinkCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Paste-the-JSON config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                parsed = json.loads(user_input["credentials_json"])
                account = parsed["account"]
                devices = parsed["devices"]
                for key in ("access_token", "refresh_token", "user_id", "expires_at"):
                    if key not in account:
                        raise KeyError(key)
                # An empty list is valid JSON - get_credentials.py may simply
                # not have found a device yet (wrong home, region mismatch,
                # not paired). Don't block setup over it: create the entry
                # with zero light entities and let the user re-run the
                # helper and reconfigure once it finds the lamp(s).
                if not isinstance(devices, list):
                    raise ValueError("devices must be a list")
                for device in devices:
                    if "device_id" not in device:
                        raise KeyError("device_id")
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                errors["base"] = "invalid_json"
            else:
                await self.async_set_unique_id(account["user_id"])
                self._abort_if_unique_id_configured()
                if not devices:
                    _LOGGER.warning(
                        "Huawei HiLink (cloud): no device in the pasted JSON - "
                        "creating the entry anyway with zero light entities."
                    )
                return self.async_create_entry(
                    title="Huawei HiLink (cloud)",
                    data={"account": account, "devices": devices},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("credentials_json"): str}),
            errors=errors,
            description_placeholders={
                "helper_path": (
                    "<dossier de config HA>/custom_components/huawei_hilink_cloud/"
                    "get_credentials.py"
                ),
            },
        )
