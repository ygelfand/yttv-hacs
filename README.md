# yttv-hacs

Home Assistant custom component for YouTube TV. Talks to a
[`yttv-bridge`](https://github.com/ygelfand/yttv-bridge) daemon over local
HTTP — this repo holds the Python integration only, no protocol code.

Distributed via [HACS](https://hacs.xyz/).

## Status

## What it gives you

- `media_player` per Chromecast, with channels as `source_list`.
- `yttv.cast` and `yttv.stop` services for automations.
- Per-channel sensors (opt-in) for "what's airing now" automations.

## Install (planned)

1. Install [`yttv-bridge`](https://github.com/ygelfand/yttv-bridge) (HA
   Add-on or Docker).
2. HACS → Custom Repositories → add this repo, category Integration.
3. Settings → Devices & Services → Add Integration → "YouTube TV (yttv-bridge)".
4. Provide the bridge URL (e.g. `http://localhost:8765`).
