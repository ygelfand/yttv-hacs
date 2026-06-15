"""Constants for the yttv-bridge integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "yttv"

CONF_BRIDGE_URL = "bridge_url"

DEFAULT_BRIDGE_URL = "http://localhost:8765"

UPDATE_INTERVAL = timedelta(seconds=60)

SERVICE_CAST = "cast"
SERVICE_STOP = "stop"

ATTR_DEVICE = "device"
ATTR_CHANNEL = "channel"

CONF_ENABLE_SENSORS = "enable_sensors"
CONF_PINNED_CHANNELS = "pinned_channels"

DEFAULT_ENABLE_SENSORS = False
