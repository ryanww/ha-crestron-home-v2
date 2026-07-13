"""Constants for the Crestron Home (CRPC bridge) integration."""
from typing import Final

from homeassistant.const import (
    Platform,
)

# Base component constants
DOMAIN: Final = "crestron_home"
MANUFACTURER: Final = "Crestron"
MODEL: Final = "Crestron Home OS (CRPC bridge)"
ATTRIBUTION: Final = "Data provided by the CRPC bridge add-on"

# Platforms
PLATFORMS: Final = [
    Platform.LIGHT,
    Platform.COVER,
    Platform.SCENE,
    Platform.CLIMATE,
    Platform.MEDIA_PLAYER,
    Platform.BINARY_SENSOR,
]

# Configuration and options
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_API_TOKEN: Final = "api_token"
CONF_ENABLED_DEVICE_TYPES: Final = "enabled_device_types"
CONF_IGNORED_DEVICE_NAMES: Final = "ignored_device_names"

# Defaults
DEFAULT_PORT: Final = 3131
DEFAULT_IGNORED_DEVICE_NAMES: Final = []

# Safety-net full refresh interval (seconds). State normally arrives via the
# bridge websocket push feed; this poll only guards against missed events.
SAFETY_REFRESH_INTERVAL: Final = 300

# Websocket reconnect backoff (seconds)
WS_BACKOFF_INITIAL: Final = 1
WS_BACKOFF_MAX: Final = 60

# Device types (used for the enabled-device-types option and coordinator data keys)
DEVICE_TYPE_LIGHT: Final = "light"
DEVICE_TYPE_SHADE: Final = "shade"
DEVICE_TYPE_SCENE: Final = "scene"
DEVICE_TYPE_CLIMATE: Final = "climate"
DEVICE_TYPE_MEDIA_PLAYER: Final = "media_player"
DEVICE_TYPE_BINARY_SENSOR: Final = "binary_sensor"

ALL_DEVICE_TYPES: Final = [
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_SHADE,
    DEVICE_TYPE_SCENE,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_MEDIA_PLAYER,
    DEVICE_TYPE_BINARY_SENSOR,
]

DEVICE_TYPE_PLATFORM_MAP: Final = {
    DEVICE_TYPE_LIGHT: Platform.LIGHT,
    DEVICE_TYPE_SHADE: Platform.COVER,
    DEVICE_TYPE_SCENE: Platform.SCENE,
    DEVICE_TYPE_CLIMATE: Platform.CLIMATE,
    DEVICE_TYPE_MEDIA_PLAYER: Platform.MEDIA_PLAYER,
    DEVICE_TYPE_BINARY_SENSOR: Platform.BINARY_SENSOR,
}

# Crestron level range (lights and shade positions)
CRESTRON_MAX_LEVEL: Final = 65535

# Websocket event types (bridge ChCrpcDeviceEvent.EventType)
EVENT_TYPE_STATE_UPDATE: Final = "stateUpdate"
EVENT_TYPE_DEVICE_ADD: Final = "deviceAdd"
EVENT_TYPE_DEVICE_DELETE: Final = "deviceDelete"
EVENT_TYPE_CONNECTED: Final = "connected"
EVENT_TYPE_DISCONNECTED: Final = "disconnected"
EVENT_TYPE_SYSTEM_ERROR: Final = "systemError"

# Websocket device types (bridge ChCrpcDeviceEvent.DeviceType)
EVENT_DEVICE_LIGHTS: Final = "IRpcLights"
EVENT_DEVICE_SHADES: Final = "IRpcShades"
EVENT_DEVICE_CLIMATE: Final = "IRpcClimate"
EVENT_DEVICE_SCENES: Final = "IRpcScenes"
EVENT_DEVICE_DOORS: Final = "IRpcDoors"
EVENT_DEVICE_MEDIA: Final = "Media"

# Startup message
STARTUP_MESSAGE: Final = f"""
-------------------------------------------------------------------
{DOMAIN}
This is a custom integration for Crestron Home via the CRPC bridge
-------------------------------------------------------------------
"""
