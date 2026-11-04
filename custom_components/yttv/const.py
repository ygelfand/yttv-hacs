"""Constants for the yttv-bridge integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "yttv"

CONF_BRIDGE_URL = "bridge_url"

DEFAULT_BRIDGE_URL = "http://localhost:8765"

UPDATE_INTERVAL = timedelta(minutes=5)

# Live thumbnails (ytimg *_live.jpg) refresh ~every 5 min (cache-control
# max-age=300). Bucket a cache-busting ?ts= param to this cadence.
LIVE_THUMB_TTL = 300

SERVICE_CAST = "cast"
SERVICE_STOP = "stop"
SERVICE_GUIDE = "guide"

ATTR_DEVICE = "device"
ATTR_CHANNEL = "channel"
ATTR_VIDEO_ID = "video_id"

CONF_ENABLE_SENSORS = "enable_sensors"
CONF_PINNED_CHANNELS = "pinned_channels"

DEFAULT_ENABLE_SENSORS = False
