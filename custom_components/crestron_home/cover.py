"""Support for Crestron Home covers/shades (via the CRPC bridge)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CrpcBridgeClient
from .const import (
    CONF_ENABLED_DEVICE_TYPES,
    CRESTRON_MAX_LEVEL,
    DEVICE_TYPE_SHADE,
    DOMAIN,
)
from .coordinator import CrestronHomeDataUpdateCoordinator
from .entity import CrestronRoomEntity, room_device_info
from .models import CrestronShade

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home covers based on config entry."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    enabled_device_types = entry.data.get(CONF_ENABLED_DEVICE_TYPES, [])
    if DEVICE_TYPE_SHADE not in enabled_device_types:
        _LOGGER.debug("Shade platform not enabled, skipping setup")
        return

    covers = []
    for device in coordinator.data.get(DEVICE_TYPE_SHADE, []):
        cover = CrestronHomeShade(coordinator, device)

        if device.ha_hidden:
            cover._attr_hidden_by = "integration"

        covers.append(cover)

    _LOGGER.debug("Adding %d cover entities", len(covers))
    async_add_entities(covers)


class CrestronHomeShade(CrestronRoomEntity, CoordinatorEntity, CoverEntity):
    """Representation of a Crestron Home shade."""

    def __init__(
        self,
        coordinator: CrestronHomeDataUpdateCoordinator,
        device: CrestronShade,
    ) -> None:
        """Initialize the shade."""
        super().__init__(coordinator)
        self._device_info = device  # Store as _device_info for CrestronRoomEntity
        self._device = device
        self._attr_unique_id = f"crestron_shade_{device.id}"
        self._attr_name = device.full_name
        self._attr_has_entity_name = False
        self._attr_device_class = CoverDeviceClass.SHADE

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        self._attr_device_info = room_device_info(
            coordinator.client.bridge_id, device.room_id, device.room
        )

    def _current(self) -> CrestronShade:
        """Return the freshest device snapshot from the coordinator."""
        for device in self.coordinator.data.get(DEVICE_TYPE_SHADE, []):
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
    def current_cover_position(self) -> int:
        """Return current position of cover (0 closed, 100 fully open)."""
        return CrpcBridgeClient.crestron_to_percentage(self._current().position)

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        return self.current_cover_position == 0

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        device = self._current()
        return device.destination > device.position

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        device = self._current()
        return device.destination < device.position

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.coordinator.client.set_shade_level(
            self._device.id, CRESTRON_MAX_LEVEL
        )
        await self.coordinator.async_command_completed()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.coordinator.client.set_shade_level(self._device.id, 0)
        await self.coordinator.async_command_completed()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover by re-targeting its current position."""
        await self.coordinator.client.set_shade_level(
            self._device.id, self._current().position
        )
        await self.coordinator.async_command_completed()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            await self.coordinator.client.set_shade_level(
                self._device.id,
                CrpcBridgeClient.percentage_to_crestron(position),
            )
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
        for device in self.coordinator.data.get(DEVICE_TYPE_SHADE, []):
            if device.id == self._device.id:
                self._device = device
                self._device_info = device
                break

        self.async_write_ha_state()
