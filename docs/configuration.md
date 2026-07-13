# Configuration

## Bridge add-on options

| Option | Required | Default | Meaning |
|---|---|---|---|
| `ch_ip` | yes | — | Crestron Home processor IP |
| `ch_port` | no | `50001` | Processor CRPC TLS port |
| `ch_password` | yes | — | Processor password |
| `ch_device_name` | no | `ha-crpc-bridge` | Client name shown in the processor's connected-devices list |

Manual container runs use the same options as environment variables
(`CH_IP`, `CH_PORT`, `CH_PASSWORD`, `CH_DEVICE_NAME`) plus `PORT` (HTTP listen
port, default 3131). Advanced env-only settings: `CH_UUID` (identity
override), `STATE_FILE` (UUID state location), and `API_TOKEN` (bearer auth
for the REST API — not supported by this integration; leave unset when using
Home Assistant).

## Integration config flow

| Field | Default | Meaning |
|---|---|---|
| Host | — | Bridge hostname or IP |
| Port | `3131` | Bridge HTTP port |
| Enabled device types | all | Which platforms to create entities for (lights, shades, scenes, thermostats, media players, doors) |
| Ignored device names | empty | Comma-separated name patterns to skip; `%` is a wildcard (e.g. `%Closet%`) |

Enabled types and ignored names can be changed later via the integration's
**Configure** button; other fields require removing and re-adding the entry.

## Security notes

- The bridge holds your processor password; the integration never sees it —
  it only ever knows the bridge host and port.
- All traffic is LAN-local. The processor connection is TLS on port 50001.
- Keep the bridge port (3131) on a trusted network segment.
