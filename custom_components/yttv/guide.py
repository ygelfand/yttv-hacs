from __future__ import annotations

import json
from typing import Any

VERSION = 2
BUDGET = 40000


def airing(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": a.get("title") or "",
        "subtitle": a.get("subtitle") or "",
        "starts_at": a.get("starts_at") or "",
        "ends_at": a.get("ends_at") or "",
    }


def channel(ch: dict[str, Any], pinned: set[str]) -> dict[str, Any]:
    cur = ch.get("current_airing")
    cur = cur if isinstance(cur, dict) else {}
    upcoming = ch.get("next_airings")
    upcoming = upcoming if isinstance(upcoming, list) else []
    name = ch.get("name") or ""
    return {
        "name": name,
        "icon": ch.get("icon_url") or "",
        "thumb": cur.get("thumbnail_url") or ch.get("live_thumbnail_url") or "",
        "live_thumb": ch.get("live_thumbnail_url") or "",
        "title": cur.get("title") or "",
        "subtitle": cur.get("subtitle") or "",
        "starts_at": cur.get("starts_at") or "",
        "ends_at": cur.get("ends_at") or "",
        "live": bool(cur.get("is_live")),
        "pinned": name in pinned,
        "next": [airing(a) for a in upcoming if isinstance(a, dict)],
    }


def page(
    channels: list[dict[str, Any]], start: int, budget: int = BUDGET
) -> tuple[list[dict[str, Any]], int | None]:
    out: list[dict[str, Any]] = []
    size = 0
    for i in range(max(start, 0), len(channels)):
        n = len(json.dumps(channels[i], ensure_ascii=True)) + 1
        if out and size + n > budget:
            return out, i
        out.append(channels[i])
        size += n
    return out, None


def guide(
    channels: list[dict[str, Any]],
    pinned: set[str],
    start: int,
    tvs: list[dict[str, Any]],
) -> dict[str, Any]:
    listed = [channel(c, pinned) for c in channels if c.get("name")]
    shown, following = page(listed, start)
    out: dict[str, Any] = {"version": VERSION, "next": following, "channels": shown}
    if start <= 0:
        out["tvs"] = tvs
    return out
