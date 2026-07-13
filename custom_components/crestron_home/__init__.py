"""The Crestron Home (CRPC bridge) integration."""
from __future__ import annotations

import logging
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)

from .api import CrpcBridgeClient, CrpcBridgeError
from .const import (
    ALL_DEVICE_TYPES,
    CONF_API_TOKEN,
    CONF_ENABLED_DEVICE_TYPES,
    CONF_HOST,
    CONF_IGNORED_DEVICE_NAMES,
    CONF_PORT,
    DEFAULT_IGNORED_DEVICE_NAMES,
    DEFAULT_PORT,
    DEVICE_TYPE_PLATFORM_MAP,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    STARTUP_MESSAGE,
)
from .coordinator import CrestronHomeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _enabled_platforms(enabled_device_types: List[str]) -> List:
    """Map enabled device types to HA platforms."""
    return [
        platform
        for device_type, platform in DEVICE_TYPE_PLATFORM_MAP.items()
        if device_type in enabled_device_types
    ]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries.

    Version 1 entries targeted the Crestron /cws/api web API directly and
    cannot be migrated automatically; the integration must be re-added and
    pointed at the CRPC bridge add-on.
    """
    if entry.version < 2:
        _LOGGER.error(
            "Config entry %s was created for the old Crestron web API and "
            "cannot be migrated. Remove the integration and add it again, "
            "pointing it at the CRPC bridge add-on",
            entry.title,
        )
        return False
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crestron Home from a config entry."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    host = entry.data.get(CONF_HOST)
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    api_token = entry.data.get(CONF_API_TOKEN, "")
    enabled_device_types = entry.data.get(
        CONF_ENABLED_DEVICE_TYPES, list(ALL_DEVICE_TYPES)
    )
    ignored_device_names = entry.data.get(
        CONF_IGNORED_DEVICE_NAMES, DEFAULT_IGNORED_DEVICE_NAMES
    )

    client = CrpcBridgeClient(hass, host, port, api_token)

    coordinator = CrestronHomeDataUpdateCoordinator(
        hass, client, enabled_device_types, ignored_device_names
    )

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except CrpcBridgeError as err:
        raise ConfigEntryNotReady(
            f"Failed to connect to CRPC bridge: {err}"
        ) from err

    # Start push updates
    coordinator.start_ws_listener()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register the CRPC bridge as the hub device
    device_registry = async_get_device_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client.bridge_id)},
        name=f"Crestron Home CRPC Bridge ({client.bridge_id})",
        manufacturer=MANUFACTURER,
        model=MODEL,
    )

    enabled_platforms = _enabled_platforms(enabled_device_types)
    _LOGGER.debug("Setting up enabled platforms: %s", enabled_platforms)
    await hass.config_entries.async_forward_entry_setups(entry, enabled_platforms)

    # Register update listener for options
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    enabled_device_types = entry.data.get(
        CONF_ENABLED_DEVICE_TYPES, list(ALL_DEVICE_TYPES)
    )
    enabled_platforms = _enabled_platforms(enabled_device_types)

    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN].get(
        entry.entry_id
    )
    if coordinator is not None:
        await coordinator.async_stop_ws_listener()

    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, enabled_platforms
    ):
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def _async_clean_entity_registry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    disabled_device_types: List[str],
) -> None:
    """Remove entities for disabled device types from the entity registry."""
    entity_registry = async_get_entity_registry(hass)

    domains_to_clean = [
        DEVICE_TYPE_PLATFORM_MAP[device_type]
        for device_type in disabled_device_types
        if device_type in DEVICE_TYPE_PLATFORM_MAP
    ]

    _LOGGER.debug("Cleaning up entities for domains: %s", domains_to_clean)

    entities_to_remove = [
        entity_id
        for entity_id, entity in entity_registry.entities.items()
        if entity.config_entry_id == entry.entry_id
        and entity.domain in domains_to_clean
    ]

    for entity_id in entities_to_remove:
        _LOGGER.debug("Removing entity %s from registry", entity_id)
        entity_registry.async_remove(entity_id)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    old_enabled_types = set(
        entry.data.get(CONF_ENABLED_DEVICE_TYPES, list(ALL_DEVICE_TYPES))
    )

    # If entry.options is empty, this is the first reload after setup
    if not entry.options:
        await async_unload_entry(hass, entry)
        await async_setup_entry(hass, entry)
        return

    new_enabled_types = set(
        entry.options.get(CONF_ENABLED_DEVICE_TYPES, old_enabled_types)
    )

    disabled_types = [t for t in old_enabled_types if t not in new_enabled_types]

    _LOGGER.debug(
        "Reloading entry. New types: %s, Disabled: %s",
        new_enabled_types,
        disabled_types,
    )

    if disabled_types:
        await _async_clean_entity_registry(hass, entry, disabled_types)

    unload_ok = await async_unload_entry(hass, entry)

    if not unload_ok:
        _LOGGER.warning("Failed to unload entry completely")
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            hass.data[DOMAIN].pop(entry.entry_id, None)

    # Update entry data with new options after unloading
    if entry.options:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **entry.options}
        )

    await async_setup_entry(hass, entry)
