"""Light entity for a Huawei HiLink Opple lamp, controlled over the cloud MQTT bridge."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HuaweiCloudRuntimeData
from .const import (
    DOMAIN,
    MAX_COLOR_TEMP_KELVIN,
    MIN_COLOR_TEMP_KELVIN,
    SERVICE_BRIGHTNESS,
    SERVICE_CCT,
    SERVICE_SWITCH,
    SIGNAL_DEVICE_UPDATE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create one light entity per configured device."""
    runtime: HuaweiCloudRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HuaweiHilinkCloudLight(runtime, device) for device in runtime.devices
    )


class HuaweiHilinkCloudLight(LightEntity):
    """An Opple lamp's switch/brightness/cct, pushed in real time (no polling)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN
    _attr_should_poll = False

    def __init__(self, runtime: HuaweiCloudRuntimeData, device: dict[str, Any]) -> None:
        self._runtime = runtime
        self._device_id = device["device_id"]
        self._attr_unique_id = device["device_id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device["device_id"])},
            name=device.get("name", "Opple lamp"),
            manufacturer="Huawei / Opple",
            model=device.get("model", "H002"),
        )
        self._is_on: bool | None = None
        self._brightness_pct: int | None = None
        self._color_temp_kelvin: int | None = None

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
        if sid == SERVICE_SWITCH and "on" in data:
            self._is_on = bool(data["on"])
        elif sid == SERVICE_BRIGHTNESS and "brightness" in data:
            self._brightness_pct = int(data["brightness"])
        elif sid == SERVICE_CCT and "colorTemperature" in data:
            self._color_temp_kelvin = int(data["colorTemperature"])
        else:
            return
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    @property
    def brightness(self) -> int | None:
        if self._brightness_pct is None:
            return None
        return round(self._brightness_pct * 255 / 100)

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._color_temp_kelvin

    async def async_turn_on(self, **kwargs: Any) -> None:
        if "color_temp_kelvin" in kwargs:
            await self._runtime.client.async_send_command(
                self._device_id, SERVICE_CCT, {"colorTemperature": kwargs["color_temp_kelvin"]}
            )
        if "brightness" in kwargs:
            brightness_pct = max(1, round(kwargs["brightness"] * 100 / 255))
            await self._runtime.client.async_send_command(
                self._device_id, SERVICE_BRIGHTNESS, {"brightness": brightness_pct}
            )
        await self._runtime.client.async_send_command(
            self._device_id, SERVICE_SWITCH, {"on": True}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._runtime.client.async_send_command(
            self._device_id, SERVICE_SWITCH, {"on": False}
        )
