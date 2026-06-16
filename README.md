# yttv-hacs

Home Assistant custom component for YouTube TV. Talks to a
[`yttv-bridge`](https://github.com/ygelfand/yttv-bridge) daemon over local
HTTP — this repo holds the Python integration only, no protocol code.
Cookies and Google account credentials stay in the bridge; they never enter
HA's config entry storage.

## What you get

- **`media_player.yttv_<chromecast>`** — one per Chromecast known to the
  bridge. `source_list` is the channel list. `select_source` casts;
  `media_stop` stops.
- **`sensor.yttv_<channel>`** — "what's airing now" per channel (opt-in).
  State = current title; attributes carry `synopsis`, `starts_at`,
  `ends_at`, `is_live`, etc. `entity_picture` is the airing thumbnail.
- **`image.yttv_<channel>`** — current-airing thumbnail as an
  [image entity](https://www.home-assistant.io/integrations/image/), so
  picture-entity / picture-glance / picture-elements cards can use it
  natively. Falls back to the station icon when nothing's airing.
- **`yttv.cast` / `yttv.stop`** services for automations.

Per-channel sensors and images are off by default — turn them on via the
options flow (Configure on the integration card) and pin the channels you
want enabled out of the box. Unpinned channels register disabled and can
be flipped on individually in the entity registry.

## Install

Prereq: a running [`yttv-bridge`](https://github.com/ygelfand/yttv-bridge)
reachable from your HA instance.

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/ygelfand/yttv-hacs`, category **Integration**.
2. Install **YouTube TV (yttv-bridge)** from HACS.
3. Restart Home Assistant.
4. Settings → Devices & Services → **Add Integration** → search
   "YouTube TV".
5. Enter the bridge URL (e.g. `http://localhost:8765`,
   `http://yttv-bridge.yttv.svc.cluster.local:8765`, or wherever yours
   lives).

## Options (Configure on the integration card)

- **Enable per-channel sensors** — also enables image entities. Off by
  default to avoid registry bloat (~120 channels).
- **Pinned channels** — multi-select; pinned channels get sensor+image
  entities enabled by default, others register disabled.

Changing options reloads the entry automatically; existing entities'
enabled state syncs to match the new pin set (entries you've manually
toggled in the UI are preserved).

## Casting from automations / dashboards

Both forms work — use whichever is more convenient:

```yaml
service: media_player.select_source
target:
  entity_id: media_player.yttv_living_room
data:
  source: ESPN
```

```yaml
service: yttv.cast
data:
  device: media_player.yttv_living_room
  channel: ESPN
```

`channel` is a substring match against the bridge's channel cache.

## Notes

- v0.1 polls `/snapshot` every 60s. The bridge doesn't push playback state
  yet, so `media_player.state` stays `idle` even while casting. Cast/stop
  actions work; only the displayed state is stale.
- No PyPI; HACS installs from git tags.
