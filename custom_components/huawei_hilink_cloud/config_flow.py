"""Config flow for the Huawei HiLink cloud (MQTT) integration.

Setup is a single paste step, same spirit as the local CoAP integration's
credential JSON paste: the user runs the (to-be-extended) local credential
helper tool out-of-band, which performs the OAuth login and prints a single
JSON blob combining the account tokens and the device list. Nothing is
typed by hand and no OAuth dance happens inside Home Assistant.

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
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


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
                if not isinstance(devices, list) or not devices:
                    raise ValueError("devices must be a non-empty list")
                for device in devices:
                    if "device_id" not in device:
                        raise KeyError("device_id")
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                errors["base"] = "invalid_json"
            else:
                await self.async_set_unique_id(account["user_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Huawei HiLink (cloud)",
                    data={"account": account, "devices": devices},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("credentials_json"): str}),
            errors=errors,
            description_placeholders={
                "helper": "credential_web.py (version étendue) ou fetch_huawei_credentials.py"
            },
        )
