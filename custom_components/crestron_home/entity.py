"""Entity base classes for the Crestron Home (CRPC bridge) integration."""
from __future__ import annotations

import logging
from typing import Optional

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, MANUFACTURER, MODEL
from .models import CrestronDevice

_LOGGER = logging.getLogger(__name__)


def room_device_info(
    bridge_id: str, room_id: int, room_name: str
) -> DeviceInfo:
    """Return the per-room HA device that entities are grouped into.

    Every entity in the same house room shares one device, named after the
    room, with suggested_area set so HA area assignment works out of the box.
    """
    name = room_name or f"Room {room_id}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{bridge_id}_room_{room_id}")},
        name=name,
        manufacturer=MANUFACTURER,
        model=MODEL,
        via_device=(DOMAIN, bridge_id),
        suggested_area=room_name or None,
    )


class CrestronRoomEntity:
    """Mixin for Crestron entities that belong to a room."""

    @property
    def room_id(self) -> Optional[int]:
        """Return the house room ID for this entity."""
        if isinstance(self._device_info, CrestronDevice):
            return self._device_info.room_id
        return None
