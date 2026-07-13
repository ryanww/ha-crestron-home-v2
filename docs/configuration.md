# Configuration

## Bridge add-on options

| Option | Required | Default | Meaning |
|---|---|---|---|
| `ch_ip` | yes | — | Crestron Home processor IP |
| `ch_port` | no | `50001` | Processor CRPC TLS port |
| `ch_password` | yes | — | Processor password |
| `ch_uuid` | no | auto | Explicit client UUID. Leave empty: the bridge generates one on first connect and reuses it for that IP+password forever (stored in `/data`) |
| `ch_device_name` | no | `ha-crpc-bridge` | Client name shown in the processor's connected-devices list |
| `api_token` | no | off | When set, every bridge request must carry it — set the same value in the integration |

Manual container runs use the same options as environment variables:
`CH_IP`, `CH_PORT`, `CH_PASSWORD`, `CH_UUID`, `CH_DEVICE_NAME`, `API_TOKEN`,
plus `PORT` (HTTP listen port, default 3131) and `STATE_FILE` (UUID state
location override).

## Integration config flow

| Field | Default | Meaning |
|---|---|---|
| Host | — | Bridge hostname or IP |
| Port | `3131` | Bridge HTTP port |
| API token | empty | Must match the bridge's `api_token` (empty if the bridge has none) |
| Enabled device types | all | Which platforms to create entities for (lights, shades, scenes, thermostats, media players, doors) |
| Ignored device names | empty | Comma-separated name patterns to skip; `%` is a wildcard (e.g. `%Closet%`) |

Enabled types and ignored names can be changed later via the integration's
**Configure** button; other fields require removing and re-adding the entry.

## Security notes

- The bridge holds your processor password; the integration never sees it —
  it only ever knows the bridge host/port/token.
- Set `api_token` whenever the bridge port is reachable beyond a trusted
  network segment. `GET /ping` is the only endpoint that skips the token.
- All traffic is LAN-local. The processor connection is TLS on port 50001.
