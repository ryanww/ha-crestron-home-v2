"""Support for Crestron Home door binary sensors (via the CRPC bridge).

The CRPC bridge exposes doors/locks/gates (IRpcDoors) with an operational
state; the old occupancy/photo sensor endpoints of the Crestron web API are
not part of the bridge and are no longer exposed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
    DEVICE_TYPE_BINARY_SENSOR,
    DOMAIN,
)
from .coordinator import CrestronHomeDataUpdateCoordinator
from .entity import CrestronRoomEntity, room_device_info
from .models import CrestronDoor

_LOGGER = logging.getLogger(__name__)

# DoorState.OperationalState values that count as "open"
OPEN_STATES = ("Open", "Opening", "PartiallyOpen")

DOOR_TYPE_DEVICE_CLASS = {
    "GarageDoor": BinarySensorDeviceClass.GARAGE_DOOR,
    "Gate": BinarySensorDeviceClass.DOOR,
    "Lock": BinarySensorDeviceClass.LOCK,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home binary sensors based on config entry."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    enabled_device_types = entry.data.get(CONF_ENABLED_DEVICE_TYPES, [])
    if DEVICE_TYPE_BINARY_SENSOR not in enabled_device_types:
        _LOGGER.debug("Binary sensor platform not enabled, skipping setup")
        return

    binary_sensors = []
    for device in coordinator.data.get(DEVICE_TYPE_BINARY_SENSOR, []):
        sensor = CrestronHomeDoorSensor(coordinator, device)

        if device.ha_hidden:
            sensor._attr_hidden_by = "integration"

        binary_sensors.append(sensor)

    _LOGGER.debug("Adding %d binary sensor entities", len(binary_sensors))
    async_add_entities(binary_sensors)


class CrestronHomeDoorSensor(CrestronRoomEntity, CoordinatorEntity, BinarySensorEntity):
    """Representation of a Crestron Home door / lock / gate state."""

    def __init__(
        self,
        coordinator: CrestronHomeDataUpdateCoordinator,
        device: CrestronDoor,
    ) -> None:
        """Initialize the door sensor."""
        super().__init__(coordinator)
        self._device_info = device  # Store as _device_info for CrestronRoomEntity
        self._device = device
        self._attr_unique_id = f"crestron_binary_sensor_{device.id}"
        self._attr_name = device.full_name
        self._attr_has_entity_name = False
        self._attr_device_class = DOOR_TYPE_DEVICE_CLASS.get(
            device.door_type, BinarySensorDeviceClass.DOOR
        )

        self._attr_device_info = room_device_info(
            coordinator.client.bridge_id, device.room_id, device.room
        )

    def _current(self) -> CrestronDoor:
        """Return the freshest device snapshot from the coordinator."""
        for device in self.coordinator.data.get(DEVICE_TYPE_BINARY_SENSOR, []):
            if device.id == self._device.id:
                return device
        return self._device

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.bridge_processor_connected:
            return False
        return self._current().is_available

    @property
    def is_on(self) -> bool:
        """Return true if the door is open (or the lock is unlocked)."""
        return self._current().operational_state in OPEN_STATES

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the raw operational state and door type."""
        device = self._current()
        return {
            "operational_state": device.operational_state,
            "door_type": device.door_type,
        }

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
        for device in self.coordinator.data.get(DEVICE_TYPE_BINARY_SENSOR, []):
            if device.id == self._device.id:
                self._device = device
                self._device_info = device
                break

        self.async_write_ha_state()
