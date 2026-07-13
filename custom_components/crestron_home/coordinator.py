"""DataUpdateCoordinator for the Crestron Home (CRPC bridge) integration.

State is pushed from the bridge websocket (/ws/json); the coordinator's
polling interval is only a slow safety net that re-fetches everything.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    CrpcBridgeAuthError,
    CrpcBridgeClient,
    CrpcBridgeConnectionError,
    CrpcBridgeError,
)
from .const import (
    DOMAIN,
    EVENT_TYPE_CONNECTED,
    EVENT_TYPE_DISCONNECTED,
    EVENT_TYPE_SYSTEM_ERROR,
    SAFETY_REFRESH_INTERVAL,
    WS_BACKOFF_INITIAL,
    WS_BACKOFF_MAX,
)
from .device_manager import CrestronDeviceManager

_LOGGER = logging.getLogger(__name__)


class CrestronHomeDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage bridge data: push updates via websocket, slow safety-net poll."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CrpcBridgeClient,
        enabled_device_types: List[str],
        ignored_device_names: Optional[List[str]] = None,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.enabled_device_types = enabled_device_types
        self.ignored_device_names = ignored_device_names or []

        self.device_manager = CrestronDeviceManager(
            hass, client, enabled_device_types, ignored_device_names
        )

        # True while the websocket is connected AND the bridge reports the
        # Crestron processor connection is up.
        self.ws_connected: bool = False
        self.bridge_processor_connected: bool = True
        self._ws_task: Optional[asyncio.Task] = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SAFETY_REFRESH_INTERVAL),
        )

    @property
    def push_connected(self) -> bool:
        """Return True when push updates are flowing."""
        return self.ws_connected and self.bridge_processor_connected

    async def _async_update_data(self) -> Dict[str, Any]:
        """Full safety-net refresh via the device manager."""
        try:
            return await self.device_manager.async_full_refresh()
        except CrpcBridgeConnectionError as error:
            raise UpdateFailed(f"Connection error: {error}") from error
        except CrpcBridgeAuthError as error:
            raise UpdateFailed(f"Authentication error: {error}") from error
        except CrpcBridgeError as error:
            raise UpdateFailed(f"Bridge error: {error}") from error

    async def async_command_completed(self) -> None:
        """Sync state after an entity command.

        With a healthy push channel the bridge sends the resulting
        stateUpdate on its own; only fall back to polling when push is down.
        """
        if not self.push_connected:
            await self.async_request_refresh()

    # ------------------------------------------------------------- websocket

    def start_ws_listener(self) -> None:
        """Start the websocket listener background task."""
        if self._ws_task is None or self._ws_task.done():
            self._ws_task = self.hass.loop.create_task(
                self._ws_listen(), name=f"{DOMAIN}-ws-listener"
            )

    async def async_stop_ws_listener(self) -> None:
        """Stop the websocket listener background task."""
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        self.ws_connected = False

    async def _ws_listen(self) -> None:
        """Maintain the /ws/json connection with exponential backoff."""
        backoff = WS_BACKOFF_INITIAL
        while True:
            try:
                ws = await self.client.ws_connect()
            except CrpcBridgeConnectionError as error:
                _LOGGER.debug(
                    "Bridge websocket connect failed (%s), retrying in %ss",
                    error,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, WS_BACKOFF_MAX)
                continue

            _LOGGER.info("Connected to CRPC bridge websocket")
            self.ws_connected = True
            backoff = WS_BACKOFF_INITIAL
            try:
                # Re-sync everything that changed while we were disconnected.
                await self.async_request_refresh()
                await self._ws_read_loop(ws)
            except asyncio.CancelledError:
                await ws.close()
                raise
            except Exception:  # noqa: BLE001 - keep the listener alive
                _LOGGER.exception("Unexpected error in bridge websocket loop")
            finally:
                self.ws_connected = False
                if not ws.closed:
                    await ws.close()

            _LOGGER.warning(
                "CRPC bridge websocket disconnected, reconnecting in %ss", backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, WS_BACKOFF_MAX)

    async def _ws_read_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Consume events until the socket closes."""
        async for message in ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                try:
                    event = json.loads(message.data)
                except ValueError:
                    _LOGGER.debug("Ignoring non-JSON websocket message")
                    continue
                if isinstance(event, dict):
                    self._handle_event(event)
            elif message.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.ERROR,
            ):
                break

    def _handle_event(self, event: Dict[str, Any]) -> None:
        """Handle a single ChCrpcDeviceEvent from the bridge."""
        event_type = event.get("EventType", "")

        if event_type == EVENT_TYPE_CONNECTED:
            was_down = not self.bridge_processor_connected
            self.bridge_processor_connected = True
            if was_down:
                _LOGGER.info("Bridge reports Crestron processor connected")
                # Definitions/states may have changed while the processor
                # link was down; re-fetch everything.
                self.hass.async_create_task(self.async_request_refresh())
            return

        if event_type == EVENT_TYPE_DISCONNECTED:
            if self.bridge_processor_connected:
                _LOGGER.warning("Bridge reports Crestron processor disconnected")
            self.bridge_processor_connected = False
            # Push the (unchanged) snapshot so entities re-evaluate availability
            self.async_set_updated_data(self.device_manager.snapshot())
            return

        if event_type == EVENT_TYPE_SYSTEM_ERROR:
            _LOGGER.warning(
                "Bridge system error: %s", event.get("SystemErrors") or "unknown"
            )
            return

        if self.device_manager.apply_event(event):
            self.async_set_updated_data(self.device_manager.snapshot())
