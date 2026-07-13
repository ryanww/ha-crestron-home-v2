# Changelog

## 1.0.0 (2026-07-12)

### Breaking Changes

- Replaced the Crestron `/cws/api` web API client with a local **CRPC bridge** sidecar (REST + WebSocket). The integration now connects to the bridge (default port 3131), not to the Crestron processor directly; Crestron credentials live in the bridge add-on
- Config flow fields changed to `host`, `port`, and optional `api_token`; existing 0.x config entries cannot be migrated and must be re-added
- Occupancy and photo sensors were removed (not available from the CRPC feed); the `sensor` platform was dropped
- Binary sensors are now backed by IRpcDoors (door / lock / gate operational state) instead of web-API door sensors
- Entities are now grouped into one Home Assistant device per Crestron room (suggested area = room name)
- Removed the standalone `crestron_debug.py` script (web-API based)

### Features

- **Push updates**: websocket listener on `/ws/json` applies stateUpdate/deviceAdd/deviceDelete events immediately (`iot_class: local_push`); polling is reduced to a 5-minute safety-net refresh
- Automatic websocket reconnect with exponential backoff; entities become unavailable while the bridge reports the processor link down
- New **climate** platform: HVAC modes from `SupportedModes`, heat/cool/auto setpoints (deci-degree conversion, °F/°C per thermostat units), dual-setpoint auto, fan modes, HVAC action
- New **media_player** platform: one player per Crestron media room with power, volume (0-100 ↔ 0.0-1.0), mute, source list/selection via routing, transport commands, and now-playing metadata including artwork
- Optional bearer-token authentication against the bridge

### Attribution

- Based on ha-crestron-home by @ruudruud (MIT)

## 0.2.3 (2026-02-23)

### Bug Fixes

- Fixed light levels always reading as 0 by fetching state from `GET /lights` instead of relying on `GET /devices` (which doesn't return `level`)
- Fixed shade `connectionStatus` to read from `GET /shades` response instead of `GET /devices`
- Fixed device and scene name double-prefixing (room name was prepended in both `api.py` and `models.py`)

## 0.2.2 (2026-02-22)

### Bug Fixes

- Fixed login response field casing (`AuthKey` instead of `authkey`) with backwards-compatible fallback
- Fixed endpoint path casing to match API docs (`/lights/SetState`, `/shades/SetState`)
- Added HTTP 511 status code handling for session expiration (previously only 401 was handled)
- Fixed brightness conversion precision loss by using direct 0-65535 to 0-255 mapping
- Preserved original `type` and `subType` fields separately from device API responses

### Improvements

- Added response status checking for light, shade, and scene POST commands (failure/partial handling)
- Rewrote all API reference documentation from the official Crestron source

## 0.2.1 (2025-10-04)

### Bug Fixes

- Fixed issue where platforms were being set up multiple times, causing errors during integration reload
- Improved reload process to ensure platforms are properly unloaded before being set up again
- Fixed redundant enabled device types retrieval in setup process

## 0.2.0 (2025-07-04)

### Features

- Added intermediate abstraction layer between Crestron Home API and Home Assistant
- Implemented consistent device snapshot with improved state tracking
- Added support for device visibility and enabled logic
- Improved data model with standardized fields across device types

### Improvements

- Refactored coordinator to use the new abstraction layer
- Updated entity classes to work with the new device model
- Improved error handling and logging
- Enhanced documentation with technical details about the abstraction layer

### Bug Fixes

- Fixed issue where configuration options weren't properly applied after initial setup
- Added enhanced logging to track configuration changes during reload process

## 0.1.5 (2025-05-04)

### Bug Fixes

- Fixed warning about blocking call to `load_default_certs` in the event loop by moving SSL context creation to initialization

## 0.1.3 (2025-05-04)

### Improvements

- Fixed issue where entities remained in Home Assistant after removing their device type from configuration

## 0.1.2 (2025-05-04)

### Improvements

- Added room-based organization for devices on the Home Assistant dashboard

## 0.1.1 (2025-05-04)

### Bug Fixes

- Fixed device discovery issue where no devices were being detected
- Added proper mapping between Crestron device types and Home Assistant device types

## 0.1.0 (2025-05-04)

### Initial Release

- Support for Crestron Home lights (on/off, brightness)
- Support for Crestron Home shades (open, close, set position)
- Support for Crestron Home scenes
- Configuration flow for easy setup
- Automatic device discovery
