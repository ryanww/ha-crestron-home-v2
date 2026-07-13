"""API client for the CRPC bridge (local REST + websocket sidecar).

The bridge exposes the Crestron Home CRPC feed as plain HTTP JSON with
PascalCase field names (Go struct tags) and pushes device events on
``ws://<host>:<port>/ws/json``. Errors come back as ``{"error": "..."}``
with status 502 (processor failure), 400 (bad input) or 401 (bad token).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp.client_exceptions import ClientConnectorError, ClientError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class CrpcBridgeError(Exception):
    """General bridge error ({"error": ...} response or malformed reply)."""


class CrpcBridgeAuthError(CrpcBridgeError):
    """Bearer token was rejected by the bridge (401)."""


class CrpcBridgeConnectionError(CrpcBridgeError):
    """The bridge could not be reached."""


class CrpcBridgeClient:
    """Thin typed client for the CRPC bridge REST API."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        api_token: Optional[str] = None,
    ) -> None:
        """Initialize the client."""
        self.hass = hass
        #host may be pasted with a scheme; port arrives as float from HA's
        #NumberSelector — normalize both or the URL is unconnectable
        host = str(host).strip().removeprefix("http://").removeprefix("https://").strip("/")
        self.host = host
        self.port = int(port)
        self.api_token = api_token or ""
        self.base_url = f"http://{self.host}:{self.port}"
        self._session = async_get_clientsession(hass)

    @property
    def bridge_id(self) -> str:
        """Return a stable identifier for this bridge instance."""
        return f"{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        """Return the JSON websocket URL (token passed as query parameter)."""
        url = f"ws://{self.host}:{self.port}/ws/json"
        if self.api_token:
            url = f"{url}?token={self.api_token}"
        return url

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Make a request and return the decoded JSON body."""
        url = f"{self.base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 401:
                    raise CrpcBridgeAuthError("Bridge rejected the API token")
                try:
                    data = await response.json(content_type=None)
                except ValueError as error:
                    raise CrpcBridgeError(
                        f"Bridge returned non-JSON response for {path} "
                        f"(HTTP {response.status})"
                    ) from error
                if response.status >= 400 or (
                    isinstance(data, dict) and "error" in data
                ):
                    message = (
                        data.get("error", f"HTTP {response.status}")
                        if isinstance(data, dict)
                        else f"HTTP {response.status}"
                    )
                    raise CrpcBridgeError(f"Bridge error for {path}: {message}")
                return data
        except ClientConnectorError as error:
            raise CrpcBridgeConnectionError(
                f"Cannot connect to CRPC bridge at {self.base_url}: {error}"
            ) from error
        except (aiohttp.ServerTimeoutError, TimeoutError) as error:
            raise CrpcBridgeConnectionError(
                f"Timeout talking to CRPC bridge at {self.base_url}"
            ) from error
        except ClientError as error:
            raise CrpcBridgeConnectionError(
                f"Error talking to CRPC bridge: {error}"
            ) from error

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return await self._request("GET", path, params)

    async def _post(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return await self._request("POST", path, params)

    # ------------------------------------------------------------------ core

    async def get_status(self) -> Dict[str, Any]:
        """GET /crpc/status -> {"connected": bool}."""
        return await self._get("/crpc/status")

    async def get_rooms(self) -> List[Dict[str, Any]]:
        """GET /rooms/all -> [Room{Id, RoomName, ...}]."""
        return await self._get("/rooms/all") or []

    # ---------------------------------------------------------------- lights

    async def get_lights(self) -> List[Dict[str, Any]]:
        """GET /lights/all -> [LightLoadAndState]."""
        return await self._get("/lights/all") or []

    async def set_light_level(
        self, load_id: int, level: int, fade_time: int = 0
    ) -> None:
        """POST /lights/:load/setLoadLevel (level 0-65535, fadeTime ms)."""
        await self._post(
            f"/lights/{load_id}/setLoadLevel",
            {"level": level, "fadeTime": fade_time},
        )

    # ---------------------------------------------------------------- shades

    async def get_shades(self) -> List[Dict[str, Any]]:
        """GET /shades/all -> [ShadeAndState]."""
        return await self._get("/shades/all") or []

    async def set_shade_level(
        self, shade_id: int, level: int, duration: Optional[int] = None
    ) -> None:
        """POST /shades/:shadeId/setLevel (Position channel, level 0-65535)."""
        params: Dict[str, Any] = {"channel": "Position", "level": level}
        if duration is not None:
            params["duration"] = duration
        await self._post(f"/shades/{shade_id}/setLevel", params)

    # --------------------------------------------------------------- climate

    async def get_thermostats(self) -> List[Dict[str, Any]]:
        """GET /thermostat/all -> [ThermostatAndState]."""
        return await self._get("/thermostat/all") or []

    async def set_thermostat_setpoint(
        self, thermostat_id: int, mode: str, setting: int
    ) -> None:
        """POST /thermostat/:id/setSetpoint (setting in deci-degrees)."""
        await self._post(
            f"/thermostat/{thermostat_id}/setSetpoint",
            {"newMode": mode, "newSetting": setting},
        )

    async def raise_lower_setpoint(
        self, thermostat_id: int, mode: str, direction: str
    ) -> None:
        """POST /thermostat/:id/raiseLowerSetpoint."""
        await self._post(
            f"/thermostat/{thermostat_id}/raiseLowerSetpoint",
            {"newMode": mode, "direction": direction},
        )

    async def set_thermostat_fan_speed(self, thermostat_id: int, mode: str) -> None:
        """POST /thermostat/:id/setFanSpeed."""
        await self._post(
            f"/thermostat/{thermostat_id}/setFanSpeed", {"newMode": mode}
        )

    async def set_thermostat_mode(self, thermostat_id: int, mode: str) -> None:
        """POST /climate/:id/setMode (mode-only change, no setpoint)."""
        await self._post(f"/climate/{thermostat_id}/setMode", {"mode": mode})

    # ---------------------------------------------------------------- scenes

    async def get_scenes(self) -> List[Dict[str, Any]]:
        """GET /scenes/all -> [SceneAndState]."""
        return await self._get("/scenes/all") or []

    async def recall_scene(self, scene_id: int) -> None:
        """POST /scenes/:sceneId/recall."""
        await self._post(f"/scenes/{scene_id}/recall")

    # ----------------------------------------------------------------- doors

    async def get_doors(self) -> List[Dict[str, Any]]:
        """GET /doors/all -> [DoorAndState]."""
        return await self._get("/doors/all") or []

    # ----------------------------------------------------------------- media

    async def get_media_rooms(self) -> List[Dict[str, Any]]:
        """GET /media/rooms -> [MediaSmartRoom] (Id=media id, RoomId=house id)."""
        return await self._get("/media/rooms") or []

    async def get_media_sources(self) -> List[Dict[str, Any]]:
        """GET /media/sources -> [MediaSource]."""
        return await self._get("/media/sources") or []

    async def get_media_state(self) -> Dict[str, Any]:
        """GET /media/state -> MediaSubsystemState (RoomStates use house ids)."""
        return await self._get("/media/state") or {}

    async def get_now_playing(self, source_id: int) -> Dict[str, Any]:
        """GET /media/sources/:id/nowPlaying -> MediaNowPlayingInfo."""
        return await self._get(f"/media/sources/{source_id}/nowPlaying") or {}

    async def media_set_volume(self, media_room_id: int, value: int) -> None:
        """POST /media/rooms/:mediaRoomId/setVolume (value 0-100)."""
        await self._post(f"/media/rooms/{media_room_id}/setVolume", {"value": value})

    async def media_mute(self, media_room_id: int) -> None:
        """POST /media/rooms/:mediaRoomId/mute."""
        await self._post(f"/media/rooms/{media_room_id}/mute")

    async def media_unmute(self, media_room_id: int) -> None:
        """POST /media/rooms/:mediaRoomId/unmute."""
        await self._post(f"/media/rooms/{media_room_id}/unmute")

    async def media_power_off(self, media_room_id: int) -> None:
        """POST /media/rooms/:mediaRoomId/powerOff."""
        await self._post(f"/media/rooms/{media_room_id}/powerOff")

    async def media_route_default(self, media_room_id: int) -> None:
        """POST /media/rooms/:mediaRoomId/routeDefault (powers on default source)."""
        await self._post(f"/media/rooms/{media_room_id}/routeDefault")

    async def media_route_source(self, source_id: int, media_room_id: int) -> None:
        """POST /media/sources/:id/route?mediaRoomId= (select a source)."""
        await self._post(
            f"/media/sources/{source_id}/route", {"mediaRoomId": media_room_id}
        )

    async def media_send_command(self, source_id: int, command: str) -> None:
        """POST /media/sources/:id/sendCommand (Play, Pause, NextTrack, ...)."""
        await self._post(
            f"/media/sources/{source_id}/sendCommand", {"command": command}
        )

    # ------------------------------------------------------------- websocket

    async def ws_connect(self) -> aiohttp.ClientWebSocketResponse:
        """Open the /ws/json event feed."""
        try:
            return await self._session.ws_connect(self.ws_url, heartbeat=30)
        except (ClientError, OSError) as error:
            raise CrpcBridgeConnectionError(
                f"Cannot open bridge websocket: {error}"
            ) from error

    @staticmethod
    def crestron_to_percentage(value: int) -> int:
        """Convert a Crestron range value (0-65535) to percentage (0-100)."""
        if value <= 0:
            return 0
        return round((value / 65535) * 100)

    @staticmethod
    def percentage_to_crestron(value: int) -> int:
        """Convert a percentage (0-100) to Crestron range value (0-65535)."""
        if value <= 0:
            return 0
        return round((65535 * value) / 100)
