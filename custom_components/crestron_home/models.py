"""Data models for the Crestron Home (CRPC bridge) integration.

These dataclasses are thin, typed snapshots of the JSON shapes served by the
CRPC bridge (PascalCase Go struct tags). Each carries the house room id and
resolved room name so entities can be grouped per room.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CrestronDevice:
    """Common representation of a room-scoped Crestron device."""

    id: int
    name: str
    room_id: int = 0
    room: str = ""
    connection: str = "online"

    # Home Assistant specific fields
    ha_hidden: bool = False
    ha_reason: str = ""

    # Raw data from the bridge (definition + state merged)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        """Return the full name of the device including room."""
        return f"{self.room} {self.name}".strip()

    @property
    def is_available(self) -> bool:
        """Return if the device is available."""
        return self.connection != "offline"


@dataclass
class CrestronLight(CrestronDevice):
    """A light load (LightLoadAndState)."""

    level: int = 0  # ChannelLevel, 0-65535
    capabilities: List[str] = field(default_factory=list)

    @property
    def is_dimmable(self) -> bool:
        """Return True when the load supports dimming."""
        return "Dimmable" in self.capabilities


@dataclass
class CrestronShade(CrestronDevice):
    """A shade (ShadeAndState)."""

    position: int = 0  # ChannelPosition, 0-65535
    destination: int = 0  # DestinationPosition, 0-65535
    shade_type: str = ""


@dataclass
class CrestronScene(CrestronDevice):
    """A scene (SceneAndState)."""

    scene_type: str = ""
    state: str = ""  # Inactive, Recalling, Active


@dataclass
class CrestronDoor(CrestronDevice):
    """A door / lock / gate (DoorAndState)."""

    door_type: str = ""  # Lock, GarageDoor, Gate
    operational_state: str = ""  # Open, Opening, Closed, Closing, ...


@dataclass
class CrestronThermostat(CrestronDevice):
    """A thermostat (ThermostatAndState)."""

    supported_modes: List[str] = field(default_factory=list)
    supported_fan_settings: List[str] = field(default_factory=list)
    # Setpoint type -> {"MinValue", "MaxValue", "StepSize", "Units"}
    setpoint_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # State (all temperatures are deci-degrees as delivered by the bridge)
    current_temperature: Optional[int] = None
    temperature_units: str = ""  # DeciFahrenheit / DeciCelsius
    current_mode: str = ""  # Off, Heat, Cool, SingleAuto, DualAuto, AuxHeat
    # Setpoint type -> current setting (deci-degrees)
    setpoints: Dict[str, int] = field(default_factory=dict)
    current_fan_setting: str = ""
    operational_states: List[str] = field(default_factory=list)


@dataclass
class CrestronMediaSource(CrestronDevice):
    """A media source definition (MediaSource)."""

    supported_commands: List[str] = field(default_factory=list)
    has_audio: bool = False
    has_video: bool = False


@dataclass
class CrestronMediaRoom(CrestronDevice):
    """A media room (MediaSmartRoom).

    ``id`` is the MEDIA room id (used by all /media room commands);
    ``room_id`` is the HOUSE room id used for grouping/areas.
    """

    volume: int = 0  # 0-100
    is_muted: bool = False
    is_powered_on: bool = False
    source_ids: List[int] = field(default_factory=list)
    active_source_id: int = 0

    # State of the currently routed source (from /media/state SourceStates
    # or Media websocket events), if any.
    source_state: Dict[str, Any] = field(default_factory=dict)
