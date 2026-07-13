# Crestron Home v2 Documentation

Documentation for the Crestron Home v2 integration, which connects Home
Assistant to a Crestron Home processor through a local **CRPC bridge**.

## Table of Contents

- [Architecture](architecture.md) — how the bridge, the push model, and the
  integration fit together
- [Installation](installation.md) — bridge add-on first, then the integration
- [Configuration](configuration.md) — every add-on option and config-flow field
- [Entities](entities.md) — what appears in Home Assistant, per platform
- [Troubleshooting](troubleshooting.md) — common failure modes and the
  migration path from v1
- [Support](support.md)
- [Trademarks](trademarks.md)

## In one paragraph

The bridge is a small local service that speaks Crestron's native CRPC
protocol (the same protocol the Crestron Home app uses) and exposes it as a
REST API plus a JSON websocket event feed. This integration talks only to the
bridge: discovery and commands over REST, instant state updates over the
websocket (`iot_class: local_push`). Nothing leaves your network, no cloud, no
polling delay — a keypad press in the house shows up in Home Assistant the
moment the processor reports it.
