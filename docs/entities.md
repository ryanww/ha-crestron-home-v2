# Entities

Entities are grouped into one Home Assistant device per Crestron room
(`suggested_area` = the room name). Unique IDs follow
`crestron_<platform>_<id>`, so entity history survives re-adding the
integration.

## Light

One entity per lighting load. Loads with the `Dimmable` capability get
brightness (Crestron 0–65535 scaled to HA 0–255); switched loads are on/off.
Commands send the target level with an optional fade; state updates arrive by
push, including mid-ramp levels.

## Cover (shades)

One entity per shade, device class `shade`. Position 0–100 in HA maps to
Crestron 0 (closed) – 65535 (open). `is_opening`/`is_closing` derive from the
shade's destination vs. current position; stop re-targets the current
position.

## Climate

One entity per thermostat:

- **HVAC modes** from the thermostat's supported modes (`Off`, `Heat`,
  `Cool`, auto modes map to `heat_cool`)
- **Target temperature** per mode, or a low/high range in dual-auto; min/max
  and step come from the thermostat's own setpoint metadata
- **Fan modes** from the thermostat's supported fan settings
- **Current temperature/humidity** and an `hvac_action` derived from the
  operational state (heating/cooling/fan active)

## Media player

One entity per Crestron **media room**, named by its house room:

- Volume (0.0–1.0), mute, on/off (route default source / power off)
- **Source list** from the sources routable to that room; selecting routes it
- Transport controls (play/pause/stop/next/previous) when the active source
  supports them — availability follows the source's live command set
- Now-playing metadata: title, artist, album, artwork, duration/position

## Scene

One HA scene per Crestron scene; activating recalls it. Scene type and current
state (Active/Inactive/Recalling) are exposed as attributes. Whole-house
scenes appear under the special Whole House grouping.

## Binary sensor (doors)

One entity per door/lock/gate from the processor's doors interface, device
class chosen by the Crestron door type. `on` means open (or opening /
partially open); the raw operational state is an attribute.

## What v1 had that v2 does not

Occupancy and photocell sensors: the CRPC feed does not expose the web API's
generic sensor list, so the `sensor` platform was removed. Door state moved to
the binary sensors above (previously sourced from the web API's sensor list).
