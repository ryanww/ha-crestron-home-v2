# Architecture

```
┌───────────────────┐  CRPC (TLS :50001)  ┌──────────────────┐  REST + WebSocket  ┌────────────────┐
│ Crestron Home     │◄───────────────────►│  CRPC Bridge      │◄──────────────────►│ Home Assistant │
│ processor (CP4-R, │                     │  (add-on /        │   :3131            │ (this          │
│ MC4-R, ...)       │                     │   container)      │                    │  integration)  │
└───────────────────┘                     └──────────────────┘                    └────────────────┘
```

## The bridge

The bridge maintains one persistent, authenticated CRPC session to the
processor — the same native protocol Crestron's own app uses. It registers as
a client device with a stable UUID (generated on first connect and persisted),
so the processor treats every bridge restart as the *same* client resuming,
not a parade of new ones.

It exposes two things on your LAN:

- **REST** (`http://<bridge>:3131`) — device lists, live state reads, and
  commands. State reads are true ask-and-reply against the processor; the
  bridge never serves stale cached state.
- **WebSocket** (`ws://<bridge>:3131/ws/json`) — every device event the
  processor pushes (level changes, scene recalls, thermostat updates, media
  transport...) forwarded as one JSON message each, typically within
  milliseconds.

## Push, not polling

The integration opens the websocket at startup and applies events to entities
immediately (`iot_class: local_push`). A full re-fetch runs every 5 minutes
purely as a safety net for missed events, and after reconnects. If the bridge
or the processor link drops, entities become unavailable until it returns; the
websocket reconnects automatically with backoff.

## Two room-ID spaces (media)

Crestron's media subsystem has its own room objects with their own IDs,
distinct from the architectural ("house") rooms:

- **House room ID** — what rooms, lights, shades, scenes, and thermostats use.
- **Media room ID** — what media routing/volume/power commands use.

Each media room knows its house room. The integration keys `media_player`
entities by the media room ID but names and areas them by the house room, so
you never see the distinction — it only matters if you call the bridge's REST
API directly.

## Units worth knowing

- **Light levels** are 0–65535 on the Crestron side; Home Assistant's 0–255
  brightness is scaled automatically.
- **Shade positions** are 0 (closed) to 65535 (open); HA's 0–100 is scaled.
- **Temperatures** travel as deci-degrees (`785` = 78.5°) with the unit
  (`DeciFahrenheit`/`DeciCelsius`) declared per thermostat; the integration
  converts both ways.
- **Media volume** is 0–100 on the bridge, mapped to HA's 0.0–1.0.
