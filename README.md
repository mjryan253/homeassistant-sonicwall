# SonicWall integration for Home Assistant

A Home Assistant custom integration that polls a SonicWall firewall over its built-in SonicOS REST/JSON API (HTTPS) and exposes device-health and per-WAN-interface throughput as sensors.

**Tested against:** SonicWall TZ350 running SonicOS Enhanced 6.5.4.5-53n.
**Should also work on** any Gen 6 SonicWall on SonicOS 6.5.4.4 or newer (TZ-300/350/400/500/600, NSA-2600/3600/etc., SOHO-250). Newer SonicOS 7.x devices may need a separate code path — this v1 only targets 6.5.x.

## What you get

- **Device sensors:** firmware version, CPU utilisation (%), connection-table usage (%), active firewall connection count, uptime (seconds).
- **Per-interface byte counters:** RX bytes and TX bytes (cumulative, total-increasing) for every IPv4 interface the firewall reports — typically `X0` (LAN) through `X4`. Disable the ones you don't care about (e.g. unused OPT ports) in the entity registry.
- **Per-interface link binary_sensors:** link state (`connectivity` device class) for `X0` and `X1` by default. Edit the `LINK_INTERFACES` tuple in `binary_sensor.py` to expose more. Source: the `status` field of `/api/sonicos/reporting/interfaces/ip` (`"1 Gbps Full Duplex"` etc → on, `"No link"` → off).

Read-only. No controls. The integration logs into the firewall's *non-config* admin mode and will not preempt your GUI admin session.

> **Not exposed, by limitation of the SonicOS 6.5 API:**
> RAM utilisation. `/api/sonicos/reporting/system` returns only the static spec string (`"1 GB RAM, 64 MB Flash"`) on Gen 6 — there's no live memory-usage figure to surface.

## Prerequisites: enable the SonicOS API on your firewall

Once-off, in the firewall web UI:

1. Switch to the **MANAGE** view (top tab).
2. Go to **Appliance → Base Settings**.
3. Find the **SonicOS API** section.
4. Tick **Enable SonicOS API**.
5. Tick **HTTP Basic** under the supported authentication methods. Leave the other auth methods unchecked unless you have another reason to enable them.
6. Click **ACCEPT**.
7. **Create a dedicated admin user for Home Assistant** (e.g. `ha-monitor`) with a long, unique password used by nothing else. Add it to the **`SonicWALL Administrators`** group — *not* `Limited Administrators` and *not* `Read-Only Admins`. SonicOS 6.5 rejects both of those at the API with `E_UNAUTHORIZED ("Limited admin access is not currently supported.")` even though they can log into the GUI fine. Only full `SonicWALL Administrators` is accepted by the API on Gen 6 — that's a SonicWall design constraint, not an integration choice. Mitigation: this integration only ever issues `GET` requests, so the elevated group membership isn't actively used; isolating it to a dedicated account at least keeps it off your day-to-day admin login.

## Installation (HACS)

1. In HACS, add this repository as a custom integration repository: `https://github.com/mjryan253/homeassistant-sonicwall`.
2. Search HACS for **SonicWall** and install.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for **SonicWall**.
5. Enter:
   - **Host or IP address** — your firewall's LAN IP (e.g. `192.168.168.168`).
   - **HTTPS port** — `443` unless you've changed it.
   - **Admin username** and **password** — the dedicated read-only account you created above.
   - **Verify SSL certificate** — leave **off** unless you've installed a publicly-trusted cert on the firewall (the factory cert is self-signed).
6. The integration will appear under Devices, identified by the firewall's serial number.

## Polling interval

Defaults to 30 seconds, which is reasonable for a LAN-local device and gives byte counters meaningful resolution. Adjust later via the integration's options if needed.

## Troubleshooting

- **"Unable to connect"** — check that the SonicOS API toggle is enabled, that you can reach `https://<firewall>/api/sonicos/version` from a browser on the same network, and that you typed the host/port correctly.
- **"Username/password wrong"** — confirm the account is *enabled for management* on at least the LAN zone, and that it has user-management or limited-admin privileges. Full-admin users also work.
- **HA log shows `aiohttp.ClientConnectorSSLError`** — turn off "Verify SSL certificate" in the integration's config (TZ-series ships with a self-signed cert).

## Development

This repo started life as a fork of [`ludeeus/integration_blueprint`](https://github.com/ludeeus/integration_blueprint); the standard blueprint dev workflow applies:

- `scripts/setup` — install Python deps for development.
- `scripts/develop` — boot a local Home Assistant instance from `./config/` with this integration loaded.
- `scripts/lint` — run ruff check + format.

The recommended dev environment is the included `.devcontainer.json` (Python 3.14 + Home Assistant 2026.3.x + ruff 0.15.x).

## License

MIT — see [LICENSE](LICENSE).
