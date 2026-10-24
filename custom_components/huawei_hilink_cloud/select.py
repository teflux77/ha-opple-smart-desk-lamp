"""Select entity for an Opple lamp's lighting scene (lightMode service).

Mapping confirmed by friTap TLS-key capture while tapping each scene button
in the Huawei AI Life app (2026-10-24 - see the project doc "Lampes Opple
HiLink - Reverse engineering Home Assistant" for the full capture log):

    Reading  -> mode 2
    Writing  -> mode 3
    Computer -> mode 4
    Custom   -> mode 6

Modes 1 and 5 were never tapped during that capture (the numbering isn't
contiguous - 1 and 5 are genuine gaps, not off-by-one). They're exposed as
"Mode 1"/"Mode 5" placeholders so the select is still usable end-to-end;
rename LIGHT_MODE_BY_OPTION (and the matching translations) once their real
names are confirmed, same capture method, same lamp.

Note: the "Side Lamp" button in the app does NOT go through lightMode at
all - it toggles the `backlight` service ({"on": bool}), already covered by
switch.py.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HuaweiCloudRuntimeData
from .const import DOMAIN, SERVICE_LIGHT_MODE, SIGNAL_DEVICE_UPDATE

_LOGGER = logging.getLogger(__name__)

LIGHT_MODE_BY_OPTION: dict[str, int] = {
    "mode_1": 1,
    "reading": 2,
    "writing": 3,
    "computer": 4,
    "mode_5": 5,
    "custom": 6,
}
OPTION_BY_LIGHT_MODE: dict[int, str] = {v: k for k, v in LIGHT_MODE_BY_OPTION.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create one lightMode select entity per configured device."""
    runtime: HuaweiCloudRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HuaweiHilinkCloudLightModeSelect(runtime, device) for device in runtime.devices
    )


class HuaweiHilinkCloudLightModeSelect(SelectEntity):
    """The lamp's lighting scene (lightMode), pushed in real time."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "light_mode"
    _attr_options = list(LIGHT_MODE_BY_OPTION.keys())

    def __init__(self, runtime: HuaweiCloudRuntimeData, device: dict[str, Any]) -> None:
        self._runtime = runtime
        self._device_id = device["device_id"]
        self._attr_unique_id = f"{device['device_id']}_{SERVICE_LIGHT_MODE}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device["device_id"])},
            name=device.get("name", "Opple lamp"),
            manufacturer="Huawei / Opple",
            model=device.get("model", "H002"),
        )
        self._current_option: str | None = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DEVICE_UPDATE.format(device_id=self._device_id),
                self._handle_device_update,
            )
        )

    @callback
    def _handle_device_update(self, sid: str, data: dict[str, Any]) -> None:
        if sid != SERVICE_LIGHT_MODE or "mode" not in data:
            return
        try:
            mode = int(data["mode"])
        except (TypeError, ValueError):
            return
        option = OPTION_BY_LIGHT_MODE.get(mode)
        if option is None:
            _LOGGER.debug(
                "Unknown lightMode value %s from device %s (not in %s)",
                mode,
                self._device_id,
                sorted(OPTION_BY_LIGHT_MODE),
            )
            return
        self._current_option = option
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        mode = LIGHT_MODE_BY_OPTION[option]
        await self._runtime.client.async_send_command(
            self._device_id, SERVICE_LIGHT_MODE, {"mode": mode}
        )
