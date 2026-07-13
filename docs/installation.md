# Installation

Two pieces, installed in this order:

1. **The CRPC bridge** — a local service that talks to your processor
2. **This integration** — talks to the bridge

## Prerequisites

- A Crestron Home processor (CP4-R, MC4-R, ...) reachable on your LAN, and its
  installer/admin password
- Home Assistant 2024.11 or newer
- For the add-on path: Home Assistant OS or a Supervised install. On
  HA Container/Core, run the bridge's Docker image yourself (same image, same
  options via environment variables)

## Step 1 — Install the bridge add-on

1. Settings → Add-ons → Add-on Store → ⋮ → **Repositories**, add
   `https://github.com/ryanww/ha-crpc-bridge-addon`.
2. Install **Crestron CRPC Bridge** from the store.
3. Open its **Configuration** tab and set:
   - **Processor IP address** and **Processor password**
   (the bridge generates and persists its own stable client identity — no
   UUID or token to manage)
4. Start the add-on and check its **Log** tab — you should see
   `Connected to CH Processor` and `Crpc.Register ok`.

Running the container manually instead (HA Container/Core):

```sh
docker run -d --name crpc-bridge \
  -e CH_IP=<processor-ip> -e CH_PASSWORD='<password>' \
  -v crpc-bridge-data:/data -p 3131:3131 ghcr.io/ryanww/wms_ha-crestron-crpc-bridge
```

The `/data` volume is what keeps the generated client UUID stable across
restarts.

## Step 2 — Install the integration

1. HACS → Integrations → ⋮ → **Custom repositories**, add
   `https://github.com/ryanww/ha-crestron-home-v2` (category: Integration).
2. Install **Crestron Home v2 (CRPC Bridge)** and restart Home Assistant.
3. Settings → Devices & Services → **Add Integration** → "Crestron Home".
4. Enter the bridge host and port:
   - Add-on on HA OS: the add-on hostname shown on its Info tab, or your HA
     host's IP; port `3131`
   - Manual container: that host's IP and mapped port
5. Pick which device types to expose, and optionally name patterns to ignore
   (`%` is a wildcard).

Entities appear grouped into one Home Assistant device per Crestron room, with
the room name as the suggested area.

## Upgrading the bridge vs. the integration

They version independently. The integration only depends on the bridge's REST
and websocket contract, so updating one rarely requires the other — release
notes will call it out when it does.
