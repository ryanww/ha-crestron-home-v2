# ha-crestron-home-v2 — Crestron Home (CRPC Bridge) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

This repository contains a custom component for Home Assistant that integrates with Crestron Home systems through a local **CRPC bridge** sidecar (a Go server that speaks the native Crestron CRPC protocol and exposes it as REST + WebSocket, typically running as a Home Assistant add-on).

Based on [ha-crestron-home](https://github.com/ruudruud/ha-crestron-home) by @ruudruud, MIT.

## Overview

Instead of polling the Crestron `/cws/api` web API, this integration talks to the CRPC bridge on your local network:

- **REST** (`http://<bridge>:<port>`) for discovery and commands
- **WebSocket** (`ws://<bridge>:<port>/ws/json`) for instant push state updates (`iot_class: local_push`)

State changes made on Crestron keypads, the Crestron Home app, or by schedules appear in Home Assistant immediately. A slow safety-net refresh (every 5 minutes) re-fetches everything in case an event was missed.

## Features

- **Lights**: dimmers (brightness) and switched loads (on/off)
- **Shades**: open, close, stop, set position (with opening/closing feedback)
- **Scenes**: recall any Crestron Home scene (light, shade, media scenes)
- **Climate**: thermostats — HVAC mode, heat/cool/auto setpoints (including dual-setpoint auto), fan mode, current temperature, and HVAC action
- **Media Players**: one player per Crestron media room — power, volume, mute, source selection (routing), transport controls (play/pause/stop/next/previous), and now-playing metadata including artwork
- **Doors**: door/lock/gate open-closed state as binary sensors
- **Push updates**: no polling delay; the bridge pushes every device event
- **Room-Based Organization**: entities are grouped into one Home Assistant device per Crestron room, with the room name as the suggested area

### Supported Device Types

| Bridge data                | Home Assistant Entity | Features |
|----------------------------|-----------------------|----------|
| Light load (Dimmable)      | Light                 | On/Off, Brightness |
| Light load (Switched)      | Light                 | On/Off |
| Shade                      | Cover                 | Open/Close/Stop, Position |
| Scene                      | Scene                 | Recall |
| Thermostat                 | Climate               | Mode, Setpoints, Fan, Action |
| Media room                 | Media Player          | Power, Volume, Mute, Source, Transport, Now Playing |
| Door / Lock / Gate         | Binary Sensor         | Open/Closed state |

> **Note**: The occupancy and photo sensors exposed by the old Crestron web API are not part of the CRPC bridge feed and are no longer provided by this integration.

## Installation

### Step 1: Install and start the CRPC bridge add-on

The integration requires the CRPC bridge sidecar to be running and connected to your Crestron Home processor. Install the bridge as a Home Assistant add-on (or run the Go server anywhere on your network), configure it with your Crestron processor credentials, and optionally set an API token (`API_TOKEN`) on the bridge.

Verify the bridge is up by opening `http://<bridge-host>:3131/crpc/status` — it should answer `{"connected": true}`.

> All Crestron processor credentials live in the bridge add-on. The integration itself only needs to reach the bridge.

### Step 2: Install the integration (HACS recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Go to HACS > Integrations > Click the three dots in the top right corner > Custom repositories
3. Add the URL of this repository and select "Integration" as the category
4. Click "Add"
5. Search for "Crestron Home" in the HACS Integrations page
6. Click "Install"
7. Restart Home Assistant

#### Manual Installation

1. Download the latest release from the GitHub repository
2. Extract the `custom_components/crestron_home` directory into your Home Assistant's `custom_components` directory
3. Restart Home Assistant

### Step 3: Set up the Integration

1. Go to Home Assistant > Settings > Devices & services
2. Click "Add Integration"
3. Search for "Crestron Home"
4. Enter the following information:
   - **Bridge host**: The IP address or hostname where the CRPC bridge runs (for a local add-on this is usually the add-on hostname or the HA host itself)
   - **Bridge port**: The bridge HTTP port (default: `3131`)
   - **API token** (optional): Only needed if you configured a token on the bridge
   - **Device types to include**: Lights, Shades, Scenes, Thermostats, Media Players, Doors
   - **Ignored device names** (optional): Device name patterns to exclude, `%` is a wildcard (e.g., `%bathroom%`)
5. Click "Submit"

## Requirements

- **Home Assistant Core**: Version 2024.11 or newer
- **CRPC bridge**: running and connected to the Crestron Home processor
- **Dependencies**: aiohttp 3.8.0 or newer

## Technical Details

This integration:

- Uses the CRPC bridge REST API (JSON with Crestron's PascalCase field names) for discovery and commands
- Subscribes to `ws://<bridge>/ws/json` and applies `stateUpdate` / `deviceAdd` / `deviceDelete` events directly to entities — no fast polling
- Reconnects the websocket automatically with exponential backoff and marks entities unavailable while the bridge reports the Crestron processor link as down
- Performs a full safety-net re-fetch every 5 minutes
- Passes the optional bearer token as `Authorization: Bearer <token>` (REST) and `?token=` (websocket)

### Level conversions

- Light levels and shade positions are 0–65535 on the Crestron side and converted to Home Assistant brightness (0–255) / cover position (0–100)
- Thermostat setpoints are deci-degrees on the wire (790 = 79.0°) in the unit the thermostat reports (`DeciFahrenheit` / `DeciCelsius`)
- Media room volume is 0–100 on the bridge and 0.0–1.0 in Home Assistant

### Media room vs house room ids

Crestron media rooms have their own id space. Media player entities are keyed by the **media room id** (`crestron_media_<id>`) but named and grouped by the **house room** the media room belongs to.

## Troubleshooting

### Connection Issues

- Check `http://<bridge-host>:<port>/crpc/status` from the Home Assistant host — it must return `{"connected": true}`
- If it returns `{"connected": false}`, the bridge is up but the Crestron processor link is down — check the add-on logs and processor credentials
- If you set an API token on the bridge, make sure the same token is configured in the integration

### Missing Devices

- Make sure the device types you want to control are selected in the integration configuration
- Verify that the devices are properly configured in your Crestron Home system
- Try reloading the integration to re-discover devices

### Device Type Configuration

When you configure the integration, you can select which device types to include. Here's what happens when you change these settings:

- **Adding Device Types**: When you add a device type, the integration will discover and add all devices of that type to Home Assistant.
- **Removing Device Types**: When you remove a device type, all entities of that type will be completely removed from Home Assistant. This ensures your Home Assistant instance stays clean without orphaned entities.
- **Re-adding Device Types**: If you later re-add a device type, the entities will be recreated with default settings.

> **Note**: Any customizations you made to entities (such as custom names, icons, or area assignments) will be lost when you remove their device type from the configuration. These settings will need to be reapplied if you re-add the device type later.

## Upgrading from 0.x (web API versions)

Version 1.0.0 replaces the Crestron `/cws/api` web API with the CRPC bridge. Existing config entries cannot be migrated automatically: remove the old integration entry, install and start the bridge add-on, then add the integration again pointing at the bridge.

## Contributing

Contributions are welcome! Please see the [Contributing Guidelines](CONTRIBUTING.md) for more information.

## Documentation

Full documentation lives in [docs/](docs/README.md): [architecture](docs/architecture.md), [installation](docs/installation.md), [configuration](docs/configuration.md), [entities](docs/entities.md), and [troubleshooting](docs/troubleshooting.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Based on [ha-crestron-home](https://github.com/ruudruud/ha-crestron-home) by @ruudruud, MIT.

## Changelog

See the [Changelog](CHANGELOG.md) for a history of changes to this integration.

## Acknowledgments

- [ha-crestron-home](https://github.com/ruudruud/ha-crestron-home) by @ruudruud, which this integration is based on
- The [Homebridge Crestron Home plugin](https://github.com/evgolsh/homebridge-crestron-home), which inspired the original project

## Disclaimer

This integration is an independent project and is not affiliated with, endorsed by, or approved by Crestron Electronics, Inc. All product names, trademarks, and registered trademarks are the property of their respective owners. The use of these names, trademarks, and brands does not imply endorsement.​

This software is provided "as is," without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement. In no event shall the authors or copyright holders be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software.​

Users are responsible for ensuring that their use of this integration complies with all applicable laws and regulations, as well as any agreements they have with third parties, including Crestron Electronics, Inc. It is the user's responsibility to obtain any necessary permissions or licenses before using this integration.​
