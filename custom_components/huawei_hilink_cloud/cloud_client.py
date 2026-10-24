"""Huawei HiLink cloud MQTT bridge client.

Framework-agnostic core (no Home Assistant imports), designed to be wrapped
by a HA integration afterwards (config_entry storage, coordinator/dispatcher,
entities). Testable standalone exactly like the local CoAP client.py.

Two responsibilities:
  1. Keep an OAuth access_token valid, refreshing it via refresh_token before
     it expires (HA integration persists the refreshed tokens into the
     config_entry - see on_tokens_updated callback).
  2. Maintain one persistent MQTT/TLS connection to the Huawei cloud broker,
     publish commands, and dispatch incoming notify messages (ACKs and
     deviceDataChanged pushes) to async callbacks, correlated by requestId.

Known-good, validated against the real lamp/account on 2026-10-24:
  - broker smartlife-dre.things.dbankcloud.com:8883, TLS without chain
    verification (the broker's cert is only validated by the official app via
    pinning, not a public CA - see docs/SECURITY notes in the project doc).
  - command topic: /smartHome/signaltrans/v2/categories/command
  - notify topic:  smarthome.notify.app.v1
  - envelope: {"header": {method, accessToken, mode, requestId, from, to,
    timestamp}, "body": {...}}
  - authorization_code exchange: POST .../smart-life/v2/hms-lite/token with
    body {"appId": APP_ID, "code": urllib.parse.quote(one_time_code)}.
  - refresh_token exchange (confirmed by decompiling the Huawei AI Life APK -
    com.huawei.smarthome.homeservice.manager.login.hms.b.refreshAccessToken()
    -> cafebabe.mk1.refreshAccessToken() -> RefreshTokenEntity): this is a
    SEPARATE endpoint from the code exchange, not the same /token path with a
    grant_type parameter. POST .../smart-life/v2/hms-lite/refreshToken with
    body {"appId": APP_ID, "refresh_token": <raw, not URL-encoded>}. Both
    calls need the full header set below (x-language/x-ori-app-name/
    x-phoneOs/x-requestId); omitting them makes the server reject the
    request before it even validates the body.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://smartlife-dre.things.dbankcloud.com"
TOKEN_URL = f"{BASE_URL}/smart-life/v2/hms-lite/token"
REFRESH_TOKEN_URL = f"{BASE_URL}/smart-life/v2/hms-lite/refreshToken"
APP_ID = "10406921"
APP_VERSION = "17.0.3.320"


def _hms_lite_headers() -> dict[str, str]:
    """Headers the real app sends on every hms-lite call (token + refreshToken).

    Confirmed necessary: a request missing x-language/x-ori-app-name/
    x-phoneOs/x-requestId gets rejected before the body is even validated.
    """
    return {
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

BROKER_HOST = "smartlife-dre.things.dbankcloud.com"
BROKER_PORT = 8883
COMMAND_TOPIC = "/smartHome/signaltrans/v2/categories/command"
NOTIFY_TOPIC = "smarthome.notify.app.v1"

# Refresh a bit before actual expiry to avoid racing a request against expiry.
TOKEN_REFRESH_MARGIN_SECONDS = 120
# How long to wait for a commandRsp ACK before giving up on a sent command.
COMMAND_ACK_TIMEOUT_SECONDS = 10.0


@dataclass(slots=True)
class CloudTokens:
    """Account-level OAuth material, as stored in the HA config entry."""

    access_token: str
    refresh_token: str
    user_id: str
    expires_at: float  # unix timestamp

    @property
    def expires_soon(self) -> bool:
        return time.time() >= (self.expires_at - TOKEN_REFRESH_MARGIN_SECONDS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "user_id": self.user_id,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CloudTokens":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            user_id=data["user_id"],
            expires_at=float(data["expires_at"]),
        )


class HuaweiCloudAuthError(RuntimeError):
    """Refresh failed - the stored refresh_token is probably dead; re-auth needed."""


async def refresh_access_token(
    session: aiohttp.ClientSession, tokens: CloudTokens
) -> CloudTokens:
    """Exchange a refresh_token for a new access_token.

    Confirmed against the real account on 2026-10-24 - see module docstring:
    this is a dedicated endpoint (.../hms-lite/refreshToken), not the code
    exchange endpoint with a grant_type parameter, and refresh_token is sent
    raw (not URL-encoded, unlike the one-time authorization code).
    """
    body = {
        "appId": APP_ID,
        "refresh_token": tokens.refresh_token,
    }
    async with session.post(
        REFRESH_TOKEN_URL,
        json=body,
        headers=_hms_lite_headers(),
        timeout=aiohttp.ClientTimeout(total=20),
    ) as resp:
        if resp.status != 200:
            raise HuaweiCloudAuthError(f"refresh failed, http={resp.status}")
        payload = await resp.json()
    new_access_token = payload.get("access_token")
    if not isinstance(new_access_token, str) or not new_access_token:
        raise HuaweiCloudAuthError("refresh response missing access_token")
    new_refresh_token = payload.get("refresh_token", tokens.refresh_token)
    expires_in = float(payload.get("expires_in", 3600))
    return CloudTokens(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        user_id=tokens.user_id,
        expires_at=time.time() + expires_in,
    )


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class HuaweiCloudMqttClient:
    """One persistent MQTT connection, bridged into an asyncio event loop.

    paho-mqtt's network loop runs in its own thread (loop_start()); every
    callback it fires is re-dispatched onto the asyncio loop via
    call_soon_threadsafe so the rest of the integration never touches
    non-asyncio code.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        tokens: CloudTokens,
        *,
        on_tokens_updated: Callable[[CloudTokens], Awaitable[None]] | None = None,
        on_device_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._loop = loop
        self._tokens = tokens
        self._on_tokens_updated = on_tokens_updated
        self._on_device_update = on_device_update
        self._client: mqtt.Client | None = None
        self._connected = asyncio.Event()
        self._pending_acks: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._http_session: aiohttp.ClientSession | None = None
        self._refresh_lock = asyncio.Lock()
        self._stopped = False

    # -- lifecycle -----------------------------------------------------

    async def async_start(self) -> None:
        """Connect to the broker and start the network thread."""
        self._http_session = aiohttp.ClientSession()
        await self._ensure_token_fresh()
        self._connect_mqtt()

    async def async_stop(self) -> None:
        self._stopped = True
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None

    def _connect_mqtt(self) -> None:
        client_id = str(uuid.uuid4())[:21]
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        client.username_pw_set(username=self._tokens.user_id, password=self._tokens.access_token)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_start()
        self._client = client

    # -- paho callbacks (run on paho's own thread - hop back to asyncio) ---

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        self._loop.call_soon_threadsafe(self._handle_connect, rc)

    def _handle_connect(self, rc: int) -> None:
        if rc == 0:
            _LOGGER.debug("Huawei cloud MQTT connected")
            assert self._client is not None
            self._client.subscribe(NOTIFY_TOPIC)
            self._connected.set()
        else:
            _LOGGER.warning("Huawei cloud MQTT connect failed, rc=%s", rc)
            self._connected.clear()
            if rc in (4, 5) and not self._stopped:
                # 4=bad username/password, 5=not authorized: token likely stale.
                asyncio.ensure_future(self._handle_auth_failure(), loop=self._loop)

    async def _handle_auth_failure(self) -> None:
        try:
            await self._ensure_token_fresh(force=True)
        except HuaweiCloudAuthError:
            _LOGGER.error("Huawei cloud re-auth failed; integration needs re-authentication")
            return
        if self._client is not None:
            self._client.username_pw_set(
                username=self._tokens.user_id, password=self._tokens.access_token
            )
            self._client.reconnect()

    def _on_disconnect(self, client, userdata, rc, properties=None) -> None:
        self._loop.call_soon_threadsafe(self._connected.clear)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _LOGGER.debug("Unparseable message on %s", msg.topic)
            return
        self._loop.call_soon_threadsafe(self._handle_message, payload)

    def _handle_message(self, payload: dict[str, Any]) -> None:
        header = payload.get("header", {})
        request_id = header.get("requestId")
        if request_id and request_id in self._pending_acks:
            future = self._pending_acks.pop(request_id)
            if not future.done():
                future.set_result(payload)
            return
        if header.get("notifyType") == "deviceDataChanged" and self._on_device_update:
            self._on_device_update(payload)

    # -- token refresh ---------------------------------------------------

    async def _ensure_token_fresh(self, *, force: bool = False) -> None:
        async with self._refresh_lock:
            if not force and not self._tokens.expires_soon:
                return
            assert self._http_session is not None
            new_tokens = await refresh_access_token(self._http_session, self._tokens)
            self._tokens = new_tokens
            if self._on_tokens_updated is not None:
                await self._on_tokens_updated(new_tokens)

    # -- commands ----------------------------------------------------------

    async def async_send_command(
        self, device_id: str, service_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Publish a command and wait for its commandRsp ACK."""
        await self._ensure_token_fresh()
        await self._connected.wait()
        assert self._client is not None

        request_id = str(uuid.uuid4())
        envelope = {
            "header": {
                "method": "POST",
                "accessToken": self._tokens.access_token,
                "mode": "ACK",
                "requestId": request_id,
                "from": f"/users/{self._tokens.user_id}",
                "to": f"/devices/{device_id}/services/{service_id}",
                "timestamp": _now_ts(),
            },
            "body": data,
        }
        future: asyncio.Future[dict[str, Any]] = self._loop.create_future()
        self._pending_acks[request_id] = future
        self._client.publish(COMMAND_TOPIC, json.dumps(envelope), qos=1)
        try:
            return await asyncio.wait_for(future, timeout=COMMAND_ACK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self._pending_acks.pop(request_id, None)
            raise
