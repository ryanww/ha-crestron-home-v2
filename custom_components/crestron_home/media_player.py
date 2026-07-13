"""Support for Crestron Home media rooms (via the CRPC bridge).

One media_player entity per media room (MediaSmartRoom). Entities are keyed
by the MEDIA room id but named/grouped by the HOUSE room the media room
belongs to (MediaSmartRoom.RoomId).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLED_DEVICE_TYPES,
    DEVICE_TYPE_MEDIA_PLAYER,
    DOMAIN,
)
from .coordinator import CrestronHomeDataUpdateCoordinator
from .entity import CrestronRoomEntity, room_device_info
from .models import CrestronMediaRoom

_LOGGER = logging.getLogger(__name__)

BASE_FEATURES = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
)

# Crestron source command name -> HA feature flag
COMMAND_FEATURES = {
    "Play": MediaPlayerEntityFeature.PLAY,
    "Pause": MediaPlayerEntityFeature.PAUSE,
    "PlayPause": MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE,
    "Stop": MediaPlayerEntityFeature.STOP,
    "NextTrack": MediaPlayerEntityFeature.NEXT_TRACK,
    "PreviousTrack": MediaPlayerEntityFeature.PREVIOUS_TRACK,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home media players based on config entry."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    enabled_device_types = entry.data.get(CONF_ENABLED_DEVICE_TYPES, [])
    if DEVICE_TYPE_MEDIA_PLAYER not in enabled_device_types:
        _LOGGER.debug("Media player platform not enabled, skipping setup")
        return

    players = []
    for device in coordinator.data.get(DEVICE_TYPE_MEDIA_PLAYER, []):
        player = CrestronHomeMediaPlayer(coordinator, device)

        if device.ha_hidden:
            player._attr_hidden_by = "integration"

        players.append(player)

    _LOGGER.debug("Adding %d media player entities", len(players))
    async_add_entities(players)


class CrestronHomeMediaPlayer(CrestronRoomEntity, CoordinatorEntity, MediaPlayerEntity):
    """Representation of a Crestron Home media room."""

    _attr_media_image_remotely_accessible = False

    def __init__(
        self,
        coordinator: CrestronHomeDataUpdateCoordinator,
        device: CrestronMediaRoom,
    ) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self._device_info = device  # Store as _device_info for CrestronRoomEntity
        self._device = device
        # Unique id uses the MEDIA room id (stable across house room renames)
        self._attr_unique_id = f"crestron_media_{device.id}"
        # Named after the house room the media room serves
        self._attr_name = f"{device.room or device.name} Media".strip()
        self._attr_has_entity_name = False

        self._attr_device_info = room_device_info(
            coordinator.client.bridge_id, device.room_id, device.room
        )

    def _current(self) -> CrestronMediaRoom:
        """Return the freshest device snapshot from the coordinator."""
        for device in self.coordinator.data.get(DEVICE_TYPE_MEDIA_PLAYER, []):
            if device.id == self._device.id:
                return device
        return self._device

    def _source_name(self, source_id: int) -> Optional[str]:
        """Resolve a source id to its name."""
        source = self.coordinator.device_manager.media_sources.get(source_id)
        return source.name if source else None

    def _active_source_commands(self) -> List[str]:
        """Return the effective commands of the active source.

        Effective commands = SupportedCommands minus UnavailableCommands.
        """
        device = self._current()
        source = self.coordinator.device_manager.media_sources.get(
            device.active_source_id
        )
        if source is None:
            return []
        unavailable = set(device.source_state.get("UnavailableCommands") or [])
        return [
            command
            for command in source.supported_commands
            if command not in unavailable
        ]

    def _now_playing(self) -> Dict[str, Any]:
        """Return the NowPlaying block of the active source state."""
        return self._current().source_state.get("NowPlaying") or {}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.bridge_processor_connected

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return supported features based on the active source."""
        features = BASE_FEATURES
        for command in self._active_source_commands():
            features |= COMMAND_FEATURES.get(command, MediaPlayerEntityFeature(0))
        return features

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the media room."""
        device = self._current()
        if not device.is_powered_on:
            return MediaPlayerState.OFF
        player_state = device.source_state.get("PlayerState") or []
        if "Playing" in player_state:
            return MediaPlayerState.PLAYING
        if "Paused" in player_state:
            return MediaPlayerState.PAUSED
        if "Buffering" in player_state:
            return MediaPlayerState.BUFFERING
        if "Stopped" in player_state:
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float:
        """Return the volume level (bridge volume is 0-100)."""
        return min(max(self._current().volume, 0), 100) / 100.0

    @property
    def is_volume_muted(self) -> bool:
        """Return True if the room is muted."""
        return self._current().is_muted

    @property
    def source_list(self) -> List[str]:
        """Return the list of source names available in this room."""
        names = []
        for source_id in self._current().source_ids:
            name = self._source_name(source_id)
            if name:
                names.append(name)
        return names

    @property
    def source(self) -> Optional[str]:
        """Return the currently routed source name."""
        device = self._current()
        if not device.is_powered_on or not device.active_source_id:
            return None
        return self._source_name(device.active_source_id)

    # -------------------------------------------------------------- metadata

    @property
    def media_title(self) -> Optional[str]:
        """Return the title of currently playing media."""
        now_playing = self._now_playing()
        return now_playing.get("Title") or now_playing.get("Line1Text") or None

    @property
    def media_artist(self) -> Optional[str]:
        """Return the artist of currently playing media."""
        now_playing = self._now_playing()
        return now_playing.get("Artist") or now_playing.get("Line2Text") or None

    @property
    def media_album_name(self) -> Optional[str]:
        """Return the album of currently playing media."""
        now_playing = self._now_playing()
        return now_playing.get("AlbumName") or None

    @property
    def media_channel(self) -> Optional[str]:
        """Return the station name if playing a station."""
        return self._now_playing().get("StationName") or None

    @property
    def media_image_url(self) -> Optional[str]:
        """Return the artwork URL of currently playing media."""
        return self._now_playing().get("ImageUrl") or None

    @property
    def media_duration(self) -> Optional[int]:
        """Return the duration of currently playing media in seconds."""
        duration = self._now_playing().get("Duration")
        return duration or None

    @property
    def media_position(self) -> Optional[int]:
        """Return the position of currently playing media in seconds."""
        position = self._current().source_state.get("PlayerPosition")
        return position or None

    # -------------------------------------------------------------- commands

    async def _send_source_command(self, command: str) -> None:
        """Send a transport command to the active source."""
        device = self._current()
        if not device.active_source_id:
            _LOGGER.warning(
                "No active source in media room %s to send %s to",
                device.name,
                command,
            )
            return
        await self.coordinator.client.media_send_command(
            device.active_source_id, command
        )
        await self.coordinator.async_command_completed()

    async def async_turn_on(self) -> None:
        """Turn the media room on by routing its default source."""
        await self.coordinator.client.media_route_default(self._device.id)
        await self.coordinator.async_command_completed()

    async def async_turn_off(self) -> None:
        """Turn the media room off."""
        await self.coordinator.client.media_power_off(self._device.id)
        await self.coordinator.async_command_completed()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume level (HA 0.0-1.0 -> bridge 0-100)."""
        await self.coordinator.client.media_set_volume(
            self._device.id, round(volume * 100)
        )
        await self.coordinator.async_command_completed()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the media room."""
        if mute:
            await self.coordinator.client.media_mute(self._device.id)
        else:
            await self.coordinator.client.media_unmute(self._device.id)
        await self.coordinator.async_command_completed()

    async def async_select_source(self, source: str) -> None:
        """Route the named source to this media room."""
        for source_id in self._current().source_ids:
            if self._source_name(source_id) == source:
                await self.coordinator.client.media_route_source(
                    source_id, self._device.id
                )
                await self.coordinator.async_command_completed()
                return
        _LOGGER.warning("Source %s not found for media room %s", source, self.name)

    async def async_media_play(self) -> None:
        """Send play command."""
        commands = self._active_source_commands()
        if "Play" in commands:
            await self._send_source_command("Play")
        else:
            await self._send_source_command("PlayPause")

    async def async_media_pause(self) -> None:
        """Send pause command."""
        commands = self._active_source_commands()
        if "Pause" in commands:
            await self._send_source_command("Pause")
        else:
            await self._send_source_command("PlayPause")

    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self._send_source_command("Stop")

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self._send_source_command("NextTrack")

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self._send_source_command("PreviousTrack")

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        if self._device.ha_hidden:
            entity_registry = async_get_entity_registry(self.hass)
            if entity_registry.async_get(self.entity_id):
                entity_registry.async_update_entity(
                    self.entity_id,
                    hidden_by="integration",
                )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        for device in self.coordinator.data.get(DEVICE_TYPE_MEDIA_PLAYER, []):
            if device.id == self._device.id:
                self._device = device
                self._device_info = device
                break

        self.async_write_ha_state()
