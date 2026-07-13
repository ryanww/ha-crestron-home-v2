# Troubleshooting

## Enable debug logging

```yaml
logger:
  logs:
    custom_components.crestron_home: debug
```

The bridge add-on's **Log** tab shows the processor side: connection state,
`Crpc.Register` results, and every device event received.

## Common failures

**Config flow says the bridge is unreachable**
The integration validates with `GET /crpc/status`. Check the bridge add-on is
running, the host/port are right, and nothing on the network blocks port 3131.
`curl http://<bridge>:3131/ping` should answer `{"message":"pong"}` from any
machine.

**401 / invalid auth**
The bridge was started with an `API_TOKEN` env var, which the integration does
not support — restart the bridge without it.

**Bridge runs but "processor link down"**
The bridge can't reach or authenticate to the processor. Check `ch_ip` and
`ch_password` in the add-on config and look at the add-on log — a wrong
password shows an authentication failure; a wrong IP shows dial timeouts and
retries every few seconds.

**Entities exist but never update**
Push isn't flowing. The integration reconnects the websocket automatically
with backoff and logs each attempt at debug level; state still self-heals at
the 5-minute safety refresh regardless. Persistent websocket failures with a
working REST connection usually mean a proxy or firewall is blocking the
upgrade on `/ws/json`.

**Entities became unavailable**
That's deliberate: the bridge reported the processor connection lost (the
add-on log will show the disconnect and its reconnect attempts), or the bridge
itself went down. Everything recovers automatically when the link returns.

**A device is missing**
Check the integration's enabled device types and ignored-name patterns
(Settings → Devices & Services → Crestron Home → Configure). Then confirm the
device exists on the bridge: `curl http://<bridge>:3131/lights/all` (or `/shades/all`, `/thermostat/all`,
`/scenes/all`, `/doors/all`, `/media/rooms`).

## Migrating from v1 (the web-API integration)

Config entries cannot be migrated — the v1 entry stored Crestron web-API
credentials, which the v2 integration doesn't use.

1. Remove the old integration entry (and the old HACS repository).
2. Install and start the bridge add-on.
3. Install this integration and add it, pointing at the bridge.

Entity unique IDs are unchanged for lights, shades, and scenes, so those
entities keep their history and automations; climate and media player entities
are new.
