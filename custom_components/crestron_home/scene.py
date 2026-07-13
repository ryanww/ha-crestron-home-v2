"""Support for Crestron Home scenes (via the CRPC bridge)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLED_DEVICE_TYPES,
    DEVICE_TYPE_SCENE,
    DOMAIN,
)
from .coordinator import CrestronHomeDataUpdateCoordinator
from .entity import CrestronRoomEntity, room_device_info
from .models import CrestronScene

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home scenes based on config entry."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    enabled_device_types = entry.data.get(CONF_ENABLED_DEVICE_TYPES, [])
    if DEVICE_TYPE_SCENE not in enabled_device_types:
        _LOGGER.debug("Scene platform not enabled, skipping setup")
        return

    scenes = []
    for device in coordinator.data.get(DEVICE_TYPE_SCENE, []):
        scene = CrestronHomeScene(coordinator, device)

        if device.ha_hidden:
            scene._attr_hidden_by = "integration"

        scenes.append(scene)

    _LOGGER.debug("Adding %d scene entities", len(scenes))
    async_add_entities(scenes)


class CrestronHomeScene(CrestronRoomEntity, CoordinatorEntity, Scene):
    """Representation of a Crestron Home scene."""

    def __init__(
        self,
        coordinator: CrestronHomeDataUpdateCoordinator,
        device: CrestronScene,
    ) -> None:
        """Initialize the scene."""
        super().__init__(coordinator)
        self._device_info = device  # Store as _device_info for CrestronRoomEntity
        self._device = device
        self._attr_unique_id = f"crestron_scene_{device.id}"
        self._attr_name = device.full_name
        self._attr_has_entity_name = False

        self._attr_device_info = room_device_info(
            coordinator.client.bridge_id, device.room_id, device.room
        )

    @property
    def available(self) -> bool:
        """Return if entity is available (scenes only need the bridge)."""
        return self.coordinator.bridge_processor_connected

    @property
    def extra_state_attributes(self) -> dict:
        """Return the scene type and current state."""
        device = self._current()
        return {
            "scene_type": device.scene_type,
            "scene_state": device.state,
        }

    def _current(self) -> CrestronScene:
        """Return the freshest device snapshot from the coordinator."""
        for device in self.coordinator.data.get(DEVICE_TYPE_SCENE, []):
            if device.id == self._device.id:
                return device
        return self._device

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene."""
        await self.coordinator.client.recall_scene(self._device.id)
        await self.coordinator.async_command_completed()

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
        for device in self.coordinator.data.get(DEVICE_TYPE_SCENE, []):
            if device.id == self._device.id:
                self._device = device
                self._device_info = device
                break

        self.async_write_ha_state()
