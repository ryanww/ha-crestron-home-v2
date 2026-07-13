"""Support for Crestron Home thermostats (via the CRPC bridge).

Setpoints on the wire are deci-degrees (790 = 79.0) in the unit reported by
the thermostat metadata (DeciFahrenheit / DeciCelsius).
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLED_DEVICE_TYPES,
    DEVICE_TYPE_CLIMATE,
    DOMAIN,
)
from .coordinator import CrestronHomeDataUpdateCoordinator
from .entity import CrestronRoomEntity, room_device_info
from .models import CrestronThermostat

_LOGGER = logging.getLogger(__name__)

# Crestron ThermostatMode -> HA HVACMode
CRESTRON_TO_HVAC_MODE = {
    "Off": HVACMode.OFF,
    "Heat": HVACMode.HEAT,
    "Cool": HVACMode.COOL,
    "SingleAuto": HVACMode.HEAT_COOL,
    "DualAuto": HVACMode.HEAT_COOL,
    "AuxHeat": HVACMode.HEAT,
}

# Setpoint types used for single-target modes
SINGLE_SETPOINT_TYPES = ("SingleAuto", "Auto")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home thermostats based on config entry."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    enabled_device_types = entry.data.get(CONF_ENABLED_DEVICE_TYPES, [])
    if DEVICE_TYPE_CLIMATE not in enabled_device_types:
        _LOGGER.debug("Climate platform not enabled, skipping setup")
        return

    thermostats = []
    for device in coordinator.data.get(DEVICE_TYPE_CLIMATE, []):
        thermostat = CrestronHomeThermostat(coordinator, device)

        if device.ha_hidden:
            thermostat._attr_hidden_by = "integration"

        thermostats.append(thermostat)

    _LOGGER.debug("Adding %d climate entities", len(thermostats))
    async_add_entities(thermostats)


class CrestronHomeThermostat(CrestronRoomEntity, CoordinatorEntity, ClimateEntity):
    """Representation of a Crestron Home thermostat."""

    def __init__(
        self,
        coordinator: CrestronHomeDataUpdateCoordinator,
        device: CrestronThermostat,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._device_info = device  # Store as _device_info for CrestronRoomEntity
        self._device = device
        self._attr_unique_id = f"crestron_climate_{device.id}"
        self._attr_name = device.full_name
        self._attr_has_entity_name = False

        self._attr_device_info = room_device_info(
            coordinator.client.bridge_id, device.room_id, device.room
        )

        # HVAC modes (deduplicated, order preserved)
        hvac_modes: List[HVACMode] = []
        for mode in device.supported_modes:
            ha_mode = CRESTRON_TO_HVAC_MODE.get(mode)
            if ha_mode is not None and ha_mode not in hvac_modes:
                hvac_modes.append(ha_mode)
        if not hvac_modes:
            hvac_modes = [HVACMode.OFF]
        self._attr_hvac_modes = hvac_modes

        features = ClimateEntityFeature(0)
        if HVACMode.HEAT in hvac_modes or HVACMode.COOL in hvac_modes:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if "DualAuto" in device.supported_modes:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if device.supported_fan_settings:
            features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = list(device.supported_fan_settings)
        self._attr_supported_features = features

    def _current(self) -> CrestronThermostat:
        """Return the freshest device snapshot from the coordinator."""
        for device in self.coordinator.data.get(DEVICE_TYPE_CLIMATE, []):
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
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        units = self._current().temperature_units
        if "celsius" in units.lower():
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @staticmethod
    def _deci_to_degrees(value: Optional[int]) -> Optional[float]:
        """Convert deci-degrees to degrees."""
        if value is None:
            return None
        return value / 10.0

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._deci_to_degrees(self._current().current_temperature)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return CRESTRON_TO_HVAC_MODE.get(self._current().current_mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> Optional[HVACAction]:
        """Return the current HVAC action."""
        device = self._current()
        states = device.operational_states
        if "HeatActive" in states or "AuxHeatActive" in states:
            return HVACAction.HEATING
        if "CoolActive" in states:
            return HVACAction.COOLING
        if "FanActive" in states:
            return HVACAction.FAN
        if device.current_mode == "Off":
            return HVACAction.OFF
        return HVACAction.IDLE

    def _setpoint(self, setpoint_type: str) -> Optional[float]:
        """Return a named setpoint in degrees."""
        value = self._current().setpoints.get(setpoint_type)
        return self._deci_to_degrees(value)

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the single target temperature for the current mode."""
        device = self._current()
        mode = device.current_mode
        if mode in ("Heat", "AuxHeat"):
            return self._setpoint("Heat")
        if mode == "Cool":
            return self._setpoint("Cool")
        if mode == "SingleAuto":
            for setpoint_type in SINGLE_SETPOINT_TYPES:
                value = self._setpoint(setpoint_type)
                if value is not None:
                    return value
        return None

    @property
    def target_temperature_low(self) -> Optional[float]:
        """Return the low (heat) target for dual-auto mode."""
        if self._current().current_mode == "DualAuto":
            return self._setpoint("Heat")
        return None

    @property
    def target_temperature_high(self) -> Optional[float]:
        """Return the high (cool) target for dual-auto mode."""
        if self._current().current_mode == "DualAuto":
            return self._setpoint("Cool")
        return None

    @property
    def min_temp(self) -> float:
        """Return the minimum settable temperature."""
        values = [
            metadata.get("MinValue")
            for metadata in self._current().setpoint_metadata.values()
            if metadata.get("MinValue") is not None
        ]
        if values:
            return min(values) / 10.0
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum settable temperature."""
        values = [
            metadata.get("MaxValue")
            for metadata in self._current().setpoint_metadata.values()
            if metadata.get("MaxValue") is not None
        ]
        if values:
            return max(values) / 10.0
        return super().max_temp

    @property
    def fan_mode(self) -> Optional[str]:
        """Return the current fan setting."""
        return self._current().current_fan_setting or None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        device = self._current()
        if hvac_mode == HVACMode.OFF:
            crestron_mode = "Off"
        elif hvac_mode == HVACMode.HEAT:
            crestron_mode = "Heat"
        elif hvac_mode == HVACMode.COOL:
            crestron_mode = "Cool"
        elif hvac_mode == HVACMode.HEAT_COOL:
            if "DualAuto" in device.supported_modes:
                crestron_mode = "DualAuto"
            else:
                crestron_mode = "SingleAuto"
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return

        await self.coordinator.client.set_thermostat_mode(
            self._device.id, crestron_mode
        )
        await self.coordinator.async_command_completed()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature(s)."""
        client = self.coordinator.client
        device = self._current()

        low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        if low is not None:
            await client.set_thermostat_setpoint(
                self._device.id, "Heat", round(low * 10)
            )
        if high is not None:
            await client.set_thermostat_setpoint(
                self._device.id, "Cool", round(high * 10)
            )

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            mode = device.current_mode
            if mode in ("Heat", "AuxHeat"):
                setpoint_type = "Heat"
            elif mode == "Cool":
                setpoint_type = "Cool"
            elif mode == "SingleAuto":
                setpoint_type = "SingleAuto"
            else:
                _LOGGER.warning(
                    "Cannot set a single target temperature in mode %s", mode
                )
                return
            await client.set_thermostat_setpoint(
                self._device.id, setpoint_type, round(temperature * 10)
            )

        await self.coordinator.async_command_completed()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        await self.coordinator.client.set_thermostat_fan_speed(
            self._device.id, fan_mode
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
        for device in self.coordinator.data.get(DEVICE_TYPE_CLIMATE, []):
            if device.id == self._device.id:
                self._device = device
                self._device_info = device
                break

        self.async_write_ha_state()
