"""Switch entities for an Opple lamp's secondary on/off services.

Covers the two confirmed simple-switch serviceId beyond the main light:
  - backlight   : the lamp base's backlight ("side lamp"), same {"on": bool}
                  payload shape as the main switch service.
  - nightSwitch : the night-light, same payload shape (found after the main
                  reverse-engineering pass, not yet exercised on a real lamp -
                  see CLAUDE.md "Current status").
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HuaweiCloudRuntimeData
from .const import (
    DOMAIN,
    SERVICE_BACKLIGHT,
    SERVICE_NIGHT_SWITCH,
    SIGNAL_DEVICE_UPDATE,
)

_LOGGER = logging.getLogger(__name__)

DESCRIPTIONS: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(key=SERVICE_BACKLIGHT, translation_key="backlight"),
    SwitchEntityDescription(key=SERVICE_NIGHT_SWITCH, translation_key="night_switch"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create backlight/nightSwitch entities for each configured device."""
    runtime: HuaweiCloudRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HuaweiHilinkCloudSwitch(runtime, device, description)
        for device in runtime.devices
        for description in DESCRIPTIONS
    )


class HuaweiHilinkCloudSwitch(SwitchEntity):
    """A simple {"on": bool} service on an Opple lamp, pushed in real time."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        runtime: HuaweiCloudRuntimeData,
        device: dict[str, Any],
        description: SwitchEntityDescription,
    ) -> None:
        self._runtime = runtime
        self._device_id = device["device_id"]
        self.entity_description = description
        self._attr_unique_id = f"{device['device_id']}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device["device_id"])},
            name=device.get("name", "Opple lamp"),
            manufacturer="Huawei / Opple",
            model=device.get("model", "H002"),
        )
        self._is_on: bool | None = None

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
        if sid != self.entity_description.key or "on" not in data:
            return
        self._is_on = bool(data["on"])
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._runtime.client.async_send_command(
            self._device_id, self.entity_description.key, {"on": True}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._runtime.client.async_send_command(
            self._device_id, self.entity_description.key, {"on": False}
        )
