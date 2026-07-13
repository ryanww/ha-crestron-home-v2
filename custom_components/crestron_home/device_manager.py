"""Device manager for the Crestron Home (CRPC bridge) integration.

Maintains a snapshot of all devices built from the bridge REST endpoints and
kept fresh by applying websocket events in place.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant

from .api import (
    CrpcBridgeAuthError,
    CrpcBridgeClient,
    CrpcBridgeConnectionError,
    CrpcBridgeError,
)
from .const import (
    DEVICE_TYPE_BINARY_SENSOR,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_MEDIA_PLAYER,
    DEVICE_TYPE_SCENE,
    DEVICE_TYPE_SHADE,
    EVENT_DEVICE_CLIMATE,
    EVENT_DEVICE_DOORS,
    EVENT_DEVICE_LIGHTS,
    EVENT_DEVICE_MEDIA,
    EVENT_DEVICE_SCENES,
    EVENT_DEVICE_SHADES,
    EVENT_TYPE_DEVICE_ADD,
    EVENT_TYPE_DEVICE_DELETE,
    EVENT_TYPE_STATE_UPDATE,
)
from .models import (
    CrestronDevice,
    CrestronDoor,
    CrestronLight,
    CrestronMediaRoom,
    CrestronMediaSource,
    CrestronScene,
    CrestronShade,
    CrestronThermostat,
)

_LOGGER = logging.getLogger(__name__)

WHOLE_HOUSE_ROOM_ID = -1
WHOLE_HOUSE_ROOM_NAME = "Whole House"


class CrestronDeviceManager:
    """Manager for devices served by the CRPC bridge."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CrpcBridgeClient,
        enabled_device_types: List[str],
        ignored_device_names: Optional[List[str]] = None,
    ) -> None:
        """Initialize the device manager."""
        self.hass = hass
        self.client = client
        self.enabled_device_types = enabled_device_types
        self.ignored_device_names = ignored_device_names or []

        # Room id -> room name (house rooms)
        self.rooms: Dict[int, str] = {}

        # Device storage, keyed by Crestron ids
        self.lights: Dict[int, CrestronLight] = {}
        self.shades: Dict[int, CrestronShade] = {}
        self.scenes: Dict[int, CrestronScene] = {}
        self.thermostats: Dict[int, CrestronThermostat] = {}
        self.doors: Dict[int, CrestronDoor] = {}
        # Media rooms keyed by MEDIA room id (not house room id)
        self.media_rooms: Dict[int, CrestronMediaRoom] = {}
        # Media source definitions keyed by source id
        self.media_sources: Dict[int, CrestronMediaSource] = {}
        # Latest MediaSourceState keyed by source id
        self.media_source_states: Dict[int, Dict[str, Any]] = {}

        self.last_poll_time: Optional[datetime] = None

    # ----------------------------------------------------------- name filter

    def _matches_ignored_pattern(self, name: str) -> bool:
        """Check if a device name matches any of the ignored patterns.

        Supports pattern matching with % wildcard:
        - bathroom -> exact match
        - %bathroom -> ends with bathroom
        - bathroom% -> starts with bathroom
        - %bathroom% -> contains bathroom
        """
        if not self.ignored_device_names:
            return False

        name = name.lower()
        for pattern in self.ignored_device_names:
            pattern = pattern.lower()
            if pattern.startswith("%") and pattern.endswith("%"):
                if pattern[1:-1] in name:
                    return True
            elif pattern.startswith("%"):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern.endswith("%"):
                if name.startswith(pattern[:-1]):
                    return True
            elif name == pattern:
                return True
        return False

    def _update_ha_parameters(self, device: CrestronDevice, device_type: str) -> None:
        """Update hidden/visibility flags for a device."""
        if self._matches_ignored_pattern(device.full_name):
            device.ha_hidden = True
            device.ha_reason = "Device hidden by name filter"
            return
        if device_type not in self.enabled_device_types:
            device.ha_hidden = True
            device.ha_reason = "Device hidden by category filter"
            return
        device.ha_hidden = False
        device.ha_reason = ""

    def room_name(self, room_id: int) -> str:
        """Resolve a house room id to its name."""
        if room_id == WHOLE_HOUSE_ROOM_ID:
            return WHOLE_HOUSE_ROOM_NAME
        return self.rooms.get(room_id, "")

    # ---------------------------------------------------------- full refresh

    async def _fetch_optional(self, coro: Any, default: Any, what: str) -> Any:
        """Fetch an optional subsystem, tolerating processor-side errors.

        Systems without the subsystem (no thermostats, doors, media) may
        answer 502 from the bridge; that must not fail the whole refresh.
        Connection and auth problems still propagate.
        """
        try:
            return await coro
        except (CrpcBridgeConnectionError, CrpcBridgeAuthError):
            raise
        except CrpcBridgeError as error:
            _LOGGER.debug("Skipping %s during refresh: %s", what, error)
            return default

    async def async_full_refresh(self) -> Dict[str, List[Any]]:
        """Re-fetch everything from the bridge and rebuild the snapshot."""
        (
            rooms,
            lights,
            shades,
            scenes,
            thermostats,
            doors,
            media_rooms,
            media_sources,
            media_state,
        ) = await asyncio.gather(
            self.client.get_rooms(),
            self.client.get_lights(),
            self.client.get_shades(),
            self.client.get_scenes(),
            self._fetch_optional(self.client.get_thermostats(), [], "thermostats"),
            self._fetch_optional(self.client.get_doors(), [], "doors"),
            self._fetch_optional(self.client.get_media_rooms(), [], "media rooms"),
            self._fetch_optional(
                self.client.get_media_sources(), [], "media sources"
            ),
            self._fetch_optional(self.client.get_media_state(), {}, "media state"),
        )

        self.rooms = {
            room.get("Id", 0): room.get("RoomName", "") for room in rooms or []
        }

        self.lights = {}
        for item in lights or []:
            light = self._build_light(item)
            if light:
                self.lights[light.id] = light

        self.shades = {}
        for item in shades or []:
            shade = self._build_shade(item)
            if shade:
                self.shades[shade.id] = shade

        self.scenes = {}
        for item in scenes or []:
            scene = self._build_scene(item)
            if scene:
                self.scenes[scene.id] = scene

        self.thermostats = {}
        for item in thermostats or []:
            thermostat = self._build_thermostat(item)
            if thermostat:
                self.thermostats[thermostat.id] = thermostat

        self.doors = {}
        for item in doors or []:
            door = self._build_door(item)
            if door:
                self.doors[door.id] = door

        self.media_sources = {}
        for item in media_sources or []:
            source = self._build_media_source(item)
            if source:
                self.media_sources[source.id] = source

        self.media_source_states = {
            state.get("Id", 0): state
            for state in (media_state or {}).get("SourceStates") or []
            if state.get("Id")
        }

        self.media_rooms = {}
        for item in media_rooms or []:
            media_room = self._build_media_room(item)
            if media_room:
                self.media_rooms[media_room.id] = media_room

        self.last_poll_time = datetime.now()
        _LOGGER.debug(
            "Bridge refresh: %d rooms, %d lights, %d shades, %d scenes, "
            "%d thermostats, %d doors, %d media rooms, %d media sources",
            len(self.rooms),
            len(self.lights),
            len(self.shades),
            len(self.scenes),
            len(self.thermostats),
            len(self.doors),
            len(self.media_rooms),
            len(self.media_sources),
        )
        return self.snapshot()

    # -------------------------------------------------------------- builders

    def _build_light(self, item: Dict[str, Any]) -> Optional[CrestronLight]:
        """Build a light from a LightLoadAndState payload."""
        load = item.get("LightLoad") or {}
        state = item.get("LightLoadState") or {}
        load_id = load.get("Id") or state.get("LoadId")
        if not load_id:
            return None
        room_id = load.get("RoomId", 0)
        light = CrestronLight(
            id=load_id,
            name=load.get("LoadName", ""),
            room_id=room_id,
            room=self.room_name(room_id),
            capabilities=load.get("Capabilities") or [],
            level=state.get("ChannelLevel", 0),
            connection=self._device_state_to_connection(state.get("DeviceState")),
            raw_data=item,
        )
        self._update_ha_parameters(light, DEVICE_TYPE_LIGHT)
        return light

    def _build_shade(self, item: Dict[str, Any]) -> Optional[CrestronShade]:
        """Build a shade from a ShadeAndState payload."""
        shade_def = item.get("Shade") or {}
        state = item.get("ShadeState") or {}
        shade_id = shade_def.get("Id") or state.get("ShadeId")
        if not shade_id:
            return None
        room_id = shade_def.get("RoomId", 0)
        shade = CrestronShade(
            id=shade_id,
            name=shade_def.get("Name", ""),
            room_id=room_id,
            room=self.room_name(room_id),
            shade_type=shade_def.get("Type", ""),
            position=state.get("ChannelPosition", 0),
            destination=state.get("DestinationPosition", 0),
            connection=self._device_state_to_connection(state.get("DeviceState")),
            raw_data=item,
        )
        self._update_ha_parameters(shade, DEVICE_TYPE_SHADE)
        return shade

    def _build_scene(self, item: Dict[str, Any]) -> Optional[CrestronScene]:
        """Build a scene from a SceneAndState payload."""
        scene_def = item.get("Scene") or {}
        state = item.get("SceneState") or {}
        scene_id = scene_def.get("Id") or state.get("SceneId")
        if not scene_id:
            return None
        room_id = scene_def.get("RoomId", 0)
        scene = CrestronScene(
            id=scene_id,
            name=scene_def.get("SceneName", ""),
            room_id=room_id,
            room=self.room_name(room_id),
            scene_type=scene_def.get("Type", ""),
            state=state.get("State", ""),
            raw_data=item,
        )
        self._update_ha_parameters(scene, DEVICE_TYPE_SCENE)
        return scene

    def _build_thermostat(
        self, item: Dict[str, Any]
    ) -> Optional[CrestronThermostat]:
        """Build a thermostat from a ThermostatAndState payload.

        Note: the definition key on the wire is "Thermostats" (singular
        struct, plural JSON tag in the bridge).
        """
        tstat_def = item.get("Thermostats") or {}
        state = item.get("ThermostatState") or {}
        tstat_id = tstat_def.get("Id") or state.get("ThermostatId")
        if not tstat_id:
            return None
        room_id = tstat_def.get("RoomId", 0)

        setpoint_metadata: Dict[str, Dict[str, Any]] = {}
        for setpoint in tstat_def.get("SupportedSetpoints") or []:
            sp_type = setpoint.get("Type", "")
            if sp_type:
                setpoint_metadata[sp_type] = setpoint.get("Metadata") or {}

        current_temp = (state.get("CurrentTemperature") or {}).get("Value")
        temp_units = (state.get("CurrentTemperature") or {}).get("Units", "")
        if not temp_units:
            for metadata in setpoint_metadata.values():
                if metadata.get("Units"):
                    temp_units = metadata["Units"]
                    break

        setpoints = {
            sp.get("Type", ""): sp.get("CurrentSetting", 0)
            for sp in state.get("CurrentSetpointStates") or []
            if sp.get("Type")
        }

        thermostat = CrestronThermostat(
            id=tstat_id,
            name=tstat_def.get("Name", ""),
            room_id=room_id,
            room=self.room_name(room_id),
            supported_modes=tstat_def.get("SupportedModes") or [],
            supported_fan_settings=tstat_def.get("SupportedFanSettings") or [],
            setpoint_metadata=setpoint_metadata,
            current_temperature=current_temp,
            temperature_units=temp_units,
            current_mode=state.get("CurrentMode", ""),
            setpoints=setpoints,
            current_fan_setting=state.get("CurrentFanSetting", ""),
            operational_states=state.get("CurrentOperationalStates") or [],
            connection=self._device_state_to_connection(state.get("DeviceState")),
            raw_data=item,
        )
        self._update_ha_parameters(thermostat, DEVICE_TYPE_CLIMATE)
        return thermostat

    def _build_door(self, item: Dict[str, Any]) -> Optional[CrestronDoor]:
        """Build a door from a DoorAndState payload."""
        door_def = item.get("Door") or {}
        state = item.get("DoorState") or {}
        door_id = door_def.get("Id") or state.get("DoorId")
        if not door_id:
            return None
        room_id = door_def.get("RoomId", 0)
        door = CrestronDoor(
            id=door_id,
            name=door_def.get("Name", ""),
            room_id=room_id,
            room=self.room_name(room_id),
            door_type=door_def.get("DoorType", ""),
            operational_state=state.get("OperationalState", ""),
            connection=self._device_state_to_connection(state.get("DeviceState")),
            raw_data=item,
        )
        self._update_ha_parameters(door, DEVICE_TYPE_BINARY_SENSOR)
        return door

    def _build_media_source(
        self, item: Dict[str, Any]
    ) -> Optional[CrestronMediaSource]:
        """Build a media source definition from a MediaSource payload."""
        source_id = item.get("Id")
        if not source_id:
            return None
        return CrestronMediaSource(
            id=source_id,
            name=item.get("Name", ""),
            supported_commands=item.get("SupportedCommands") or [],
            has_audio=item.get("HasAudio", False),
            has_video=item.get("HasVideo", False),
            raw_data=item,
        )

    def _build_media_room(self, item: Dict[str, Any]) -> Optional[CrestronMediaRoom]:
        """Build a media room from a MediaSmartRoom payload.

        MediaSmartRoom.Id is the MEDIA room id; RoomId is the HOUSE room id.
        """
        media_id = item.get("Id")
        if not media_id:
            return None
        house_room_id = item.get("RoomId", 0)
        active_sources = item.get("ActiveSources") or []
        active_source_id = active_sources[0] if active_sources else 0
        media_room = CrestronMediaRoom(
            id=media_id,
            name=item.get("Name", ""),
            room_id=house_room_id,
            room=self.room_name(house_room_id),
            volume=item.get("Volume", 0),
            is_muted=item.get("IsMuted", False),
            is_powered_on=item.get("IsPoweredOn", False),
            source_ids=item.get("Sources") or [],
            active_source_id=active_source_id,
            source_state=self.media_source_states.get(active_source_id, {}),
            raw_data=item,
        )
        self._update_ha_parameters(media_room, DEVICE_TYPE_MEDIA_PLAYER)
        return media_room

    @staticmethod
    def _device_state_to_connection(device_state: Optional[str]) -> str:
        """Map the bridge DeviceState to the online/offline convention."""
        if device_state and device_state.lower() == "offline":
            return "offline"
        return "online"

    # -------------------------------------------------------- event handling

    def apply_event(self, event: Dict[str, Any]) -> bool:
        """Apply a websocket ChCrpcDeviceEvent. Return True if state changed.

        Unused payload fields in events are zero-valued (not omitted), so we
        key off DeviceType and non-zero ids.
        """
        event_type = event.get("EventType", "")
        if event_type not in (
            EVENT_TYPE_STATE_UPDATE,
            EVENT_TYPE_DEVICE_ADD,
            EVENT_TYPE_DEVICE_DELETE,
        ):
            return False

        device_type = event.get("DeviceType", "")
        handler = {
            EVENT_DEVICE_LIGHTS: self._apply_light_event,
            EVENT_DEVICE_SHADES: self._apply_shade_event,
            EVENT_DEVICE_CLIMATE: self._apply_climate_event,
            EVENT_DEVICE_SCENES: self._apply_scene_event,
            EVENT_DEVICE_DOORS: self._apply_door_event,
            EVENT_DEVICE_MEDIA: self._apply_media_event,
        }.get(device_type)
        if handler is None:
            return False
        return handler(event, event_type)

    def _apply_light_event(self, event: Dict[str, Any], event_type: str) -> bool:
        payload = event.get("LightLoadAndState") or {}
        state = payload.get("LightLoadState") or {}
        load_id = (payload.get("LightLoad") or {}).get("Id") or state.get("LoadId")
        if not load_id:
            return False
        if event_type == EVENT_TYPE_DEVICE_DELETE:
            return self.lights.pop(load_id, None) is not None
        existing = self.lights.get(load_id)
        if existing is None or event_type == EVENT_TYPE_DEVICE_ADD:
            light = self._build_light(payload)
            if light is None:
                return False
            # Definition may be sparse on pure state updates; keep old identity
            if existing and not (payload.get("LightLoad") or {}).get("LoadName"):
                light.name = existing.name
                light.room_id = existing.room_id
                light.room = existing.room
                light.capabilities = existing.capabilities
                self._update_ha_parameters(light, DEVICE_TYPE_LIGHT)
            self.lights[load_id] = light
            return True
        existing.level = state.get("ChannelLevel", existing.level)
        existing.connection = self._device_state_to_connection(
            state.get("DeviceState")
        )
        existing.raw_data = payload
        return True

    def _apply_shade_event(self, event: Dict[str, Any], event_type: str) -> bool:
        payload = event.get("ShadeAndState") or {}
        state = payload.get("ShadeState") or {}
        shade_id = (payload.get("Shade") or {}).get("Id") or state.get("ShadeId")
        if not shade_id:
            return False
        if event_type == EVENT_TYPE_DEVICE_DELETE:
            return self.shades.pop(shade_id, None) is not None
        existing = self.shades.get(shade_id)
        if existing is None or event_type == EVENT_TYPE_DEVICE_ADD:
            shade = self._build_shade(payload)
            if shade is None:
                return False
            if existing and not (payload.get("Shade") or {}).get("Name"):
                shade.name = existing.name
                shade.room_id = existing.room_id
                shade.room = existing.room
                self._update_ha_parameters(shade, DEVICE_TYPE_SHADE)
            self.shades[shade_id] = shade
            return True
        existing.position = state.get("ChannelPosition", existing.position)
        existing.destination = state.get(
            "DestinationPosition", existing.destination
        )
        existing.connection = self._device_state_to_connection(
            state.get("DeviceState")
        )
        existing.raw_data = payload
        return True

    def _apply_climate_event(self, event: Dict[str, Any], event_type: str) -> bool:
        payload = event.get("ThermostatAndState") or {}
        state = payload.get("ThermostatState") or {}
        tstat_id = (payload.get("Thermostats") or {}).get("Id") or state.get(
            "ThermostatId"
        )
        if not tstat_id:
            return False
        if event_type == EVENT_TYPE_DEVICE_DELETE:
            return self.thermostats.pop(tstat_id, None) is not None
        existing = self.thermostats.get(tstat_id)
        if existing is None or event_type == EVENT_TYPE_DEVICE_ADD:
            thermostat = self._build_thermostat(payload)
            if thermostat is None:
                return False
            if existing and not (payload.get("Thermostats") or {}).get("Name"):
                thermostat.name = existing.name
                thermostat.room_id = existing.room_id
                thermostat.room = existing.room
                thermostat.supported_modes = existing.supported_modes
                thermostat.supported_fan_settings = existing.supported_fan_settings
                thermostat.setpoint_metadata = existing.setpoint_metadata
                self._update_ha_parameters(thermostat, DEVICE_TYPE_CLIMATE)
            self.thermostats[tstat_id] = thermostat
            return True
        current_temp = state.get("CurrentTemperature") or {}
        if current_temp.get("Value") is not None:
            existing.current_temperature = current_temp.get("Value")
            if current_temp.get("Units"):
                existing.temperature_units = current_temp["Units"]
        if state.get("CurrentMode"):
            existing.current_mode = state["CurrentMode"]
        for setpoint in state.get("CurrentSetpointStates") or []:
            if setpoint.get("Type"):
                existing.setpoints[setpoint["Type"]] = setpoint.get(
                    "CurrentSetting", 0
                )
        if state.get("CurrentFanSetting"):
            existing.current_fan_setting = state["CurrentFanSetting"]
        if state.get("CurrentOperationalStates") is not None:
            existing.operational_states = state["CurrentOperationalStates"]
        existing.connection = self._device_state_to_connection(
            state.get("DeviceState")
        )
        existing.raw_data = payload
        return True

    def _apply_scene_event(self, event: Dict[str, Any], event_type: str) -> bool:
        payload = event.get("SceneAndState") or {}
        state = payload.get("SceneState") or {}
        scene_id = (payload.get("Scene") or {}).get("Id") or state.get("SceneId")
        if not scene_id:
            return False
        if event_type == EVENT_TYPE_DEVICE_DELETE:
            return self.scenes.pop(scene_id, None) is not None
        existing = self.scenes.get(scene_id)
        if existing is None or event_type == EVENT_TYPE_DEVICE_ADD:
            scene = self._build_scene(payload)
            if scene is None:
                return False
            if existing and not (payload.get("Scene") or {}).get("SceneName"):
                scene.name = existing.name
                scene.room_id = existing.room_id
                scene.room = existing.room
                scene.scene_type = existing.scene_type
                self._update_ha_parameters(scene, DEVICE_TYPE_SCENE)
            self.scenes[scene_id] = scene
            return True
        existing.state = state.get("State", existing.state)
        existing.raw_data = payload
        return True

    def _apply_door_event(self, event: Dict[str, Any], event_type: str) -> bool:
        payload = event.get("DoorAndState") or {}
        state = payload.get("DoorState") or {}
        door_id = (payload.get("Door") or {}).get("Id") or state.get("DoorId")
        if not door_id:
            return False
        if event_type == EVENT_TYPE_DEVICE_DELETE:
            return self.doors.pop(door_id, None) is not None
        existing = self.doors.get(door_id)
        if existing is None or event_type == EVENT_TYPE_DEVICE_ADD:
            door = self._build_door(payload)
            if door is None:
                return False
            if existing and not (payload.get("Door") or {}).get("Name"):
                door.name = existing.name
                door.room_id = existing.room_id
                door.room = existing.room
                door.door_type = existing.door_type
                self._update_ha_parameters(door, DEVICE_TYPE_BINARY_SENSOR)
            self.doors[door_id] = door
            return True
        existing.operational_state = state.get(
            "OperationalState", existing.operational_state
        )
        existing.connection = self._device_state_to_connection(
            state.get("DeviceState")
        )
        existing.raw_data = payload
        return True

    def _apply_media_event(self, event: Dict[str, Any], event_type: str) -> bool:
        """Apply a Media event: room update, source state, or nothing usable."""
        changed = False

        source_state = event.get("MediaSourceState") or {}
        source_id = source_state.get("Id", 0)
        if source_id:
            self.media_source_states[source_id] = source_state
            # Refresh source state on any media room currently playing it
            for media_room in self.media_rooms.values():
                if media_room.active_source_id == source_id:
                    media_room.source_state = source_state
                    changed = True

        room_update = event.get("MediaRoomUpdate") or {}
        media_id = room_update.get("Id", 0)
        if media_id:
            if event_type == EVENT_TYPE_DEVICE_DELETE:
                return self.media_rooms.pop(media_id, None) is not None
            media_room = self._build_media_room(room_update)
            if media_room is not None:
                existing = self.media_rooms.get(media_id)
                if existing and not room_update.get("Name"):
                    media_room.name = existing.name
                    media_room.room_id = existing.room_id
                    media_room.room = existing.room
                    self._update_ha_parameters(
                        media_room, DEVICE_TYPE_MEDIA_PLAYER
                    )
                self.media_rooms[media_id] = media_room
                changed = True

        return changed

    # -------------------------------------------------------------- snapshot

    def snapshot(self) -> Dict[str, List[Any]]:
        """Return the coordinator data snapshot, organized by device type."""
        return {
            DEVICE_TYPE_LIGHT: list(self.lights.values()),
            DEVICE_TYPE_SHADE: list(self.shades.values()),
            DEVICE_TYPE_SCENE: list(self.scenes.values()),
            DEVICE_TYPE_CLIMATE: list(self.thermostats.values()),
            DEVICE_TYPE_MEDIA_PLAYER: list(self.media_rooms.values()),
            DEVICE_TYPE_BINARY_SENSOR: list(self.doors.values()),
        }
