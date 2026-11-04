"""Thin async HTTP client for yttv-bridge."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout


class BridgeError(Exception):
    """Bridge call failed."""


class BridgeAuthError(BridgeError):
    """Bridge reported an auth problem (rotated cookies, etc.)."""


class BridgeClient:
    """Stateless wrapper around the yttv-bridge REST API."""

    def __init__(self, session: ClientSession, base_url: str) -> None:
        self._session = session
        self._base = base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base

    async def healthz(self) -> None:
        """Raise BridgeError if /healthz isn't 200 ok."""
        try:
            async with self._session.get(
                f"{self._base}/healthz", timeout=ClientTimeout(total=10)
            ) as resp:
                resp.raise_for_status()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise BridgeAuthError(str(err)) from err
            raise BridgeError(f"healthz {err.status}") from err
        except ClientError as err:
            raise BridgeError(str(err)) from err

    async def snapshot(self) -> dict[str, Any]:
        """GET /snapshot → {channels: [...], devices: [...]}."""
        try:
            async with self._session.get(
                f"{self._base}/snapshot", timeout=ClientTimeout(total=15)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise BridgeAuthError(str(err)) from err
            raise BridgeError(f"snapshot {err.status}") from err
        except ClientError as err:
            raise BridgeError(str(err)) from err

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed objects from the bridge's /events SSE stream.

        Long-lived: stays open until the connection drops or is cancelled.
        Raises BridgeError on connection failure so the caller can reconnect.
        """
        timeout = ClientTimeout(total=None, sock_connect=10, sock_read=None)
        try:
            async with self._session.get(
                f"{self._base}/events", timeout=timeout
            ) as resp:
                resp.raise_for_status()
                async for raw in resp.content:
                    line = raw.decode("utf-8").strip()
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if payload:
                            yield json.loads(payload)
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise BridgeAuthError(str(err)) from err
            raise BridgeError(f"events {err.status}") from err
        except ClientError as err:
            raise BridgeError(str(err)) from err

    async def cast(
        self,
        *,
        device: str | None = None,
        host: str | None = None,
        port: int | None = None,
        channel: str = "",
        video_id: str = "",
    ) -> None:
        """POST /cast — bridge picks device by name or host:port."""
        what = {"video_id": video_id} if video_id else {"channel": channel}
        await self._post("/cast", self._target(device, host, port) | what)

    async def stop(
        self,
        *,
        device: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """POST /stop."""
        await self._post("/stop", self._target(device, host, port))

    async def set_volume(
        self,
        *,
        device: str | None = None,
        host: str | None = None,
        port: int | None = None,
        level: float,
    ) -> None:
        """POST /volume — set device volume level (0..1)."""
        await self._post("/volume", self._target(device, host, port) | {"level": level})

    async def set_muted(
        self,
        *,
        device: str | None = None,
        host: str | None = None,
        port: int | None = None,
        muted: bool,
    ) -> None:
        """POST /mute."""
        await self._post("/mute", self._target(device, host, port) | {"muted": muted})

    async def play_pause(
        self,
        *,
        device: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """POST /playpause — toggle play/pause of the active media."""
        await self._post("/playpause", self._target(device, host, port))

    @staticmethod
    def _target(
        device: str | None, host: str | None, port: int | None
    ) -> dict[str, Any]:
        if host:
            payload: dict[str, Any] = {"host": host}
            if port:
                payload["port"] = port
            return payload
        if device:
            return {"device": device}
        raise BridgeError("device or host required")

    async def _post(self, path: str, payload: dict[str, Any]) -> None:
        try:
            async with self._session.post(
                f"{self._base}{path}",
                json=payload,
                timeout=ClientTimeout(total=70),
            ) as resp:
                resp.raise_for_status()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise BridgeAuthError(str(err)) from err
            raise BridgeError(f"{path} {err.status}") from err
        except ClientError as err:
            raise BridgeError(str(err)) from err
