"""Huawei HiLink cloud (MQTT) integration - setup/unload."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .cloud_client import CloudTokens, HuaweiCloudMqttClient
from .const import DOMAIN, PLATFORMS, SERVICE_SWITCH, SIGNAL_DEVICE_UPDATE

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class HuaweiCloudRuntimeData:
    """Runtime state kept in hass.data for this config entry."""

    client: HuaweiCloudMqttClient
    devices: list[dict[str, Any]]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start the cloud MQTT client for this account and forward to light."""
    tokens = CloudTokens.from_dict(entry.data["account"])

    async def on_tokens_updated(new_tokens: CloudTokens) -> None:
        """Persist a refreshed access_token/refresh_token into the entry."""
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "account": new_tokens.to_dict()}
        )

    def on_device_update(payload: dict[str, Any]) -> None:
        """Dispatch a deviceDataChanged push to the matching light entity."""
        body = payload.get("body", {})
        device_id = body.get("devId")
        if not device_id:
            return
        for service in body.get("services", []):
            sid = service.get("sid")
            data = service.get("data", {})
            if sid:
                async_dispatcher_send(
                    hass, SIGNAL_DEVICE_UPDATE.format(device_id=device_id), sid, data
                )

    client = HuaweiCloudMqttClient(
        hass.loop,
        tokens,
        on_tokens_updated=on_tokens_updated,
        on_device_update=on_device_update,
    )
    await client.async_start()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = HuaweiCloudRuntimeData(
        client=client, devices=entry.data["devices"]
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Entities only ever learn the lamp's state from a deviceDataChanged push
    # (see on_device_update above), which the cloud only sends after a
    # command - there's no proactive state fetch otherwise. So right after
    # (re)start/reload, everything is "unknown" until the user touches a
    # control. Fire one GET per device now (any single serviceId works - the
    # cloud replies with the FULL device state, same as after a real
    # command, per the "Validation complète du pont MQTT" findings) to
    # populate entities immediately instead of waiting. Best-effort: never
    # block or fail setup over this.
    for device in entry.data["devices"]:
        device_id = device["device_id"]

        async def _request_initial_state(device_id: str = device_id) -> None:
            try:
                await client.async_request_state(device_id, SERVICE_SWITCH)
            except Exception:  # noqa: BLE001 - startup nicety, must never crash setup
                _LOGGER.debug(
                    "Initial state query failed for device %s", device_id, exc_info=True
                )

        hass.async_create_task(_request_initial_state())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop the client and unload platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: HuaweiCloudRuntimeData = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime.client.async_stop()
    return unload_ok
