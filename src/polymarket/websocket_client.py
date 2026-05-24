"""WebSocket client for real-time Polymarket price updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine, Optional

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

logger = structlog.get_logger(__name__)

PriceCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class PolymarketWebSocket:
    """Connects to Polymarket WebSocket for real-time market data."""

    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(self, on_price_update: Optional[PriceCallback] = None) -> None:
        self._on_price_update = on_price_update
        self._running = False
        self._ws: Any = None
        self._subscribed_assets: set[str] = set()

    async def connect(self, asset_ids: list[str]) -> None:
        """Connect and subscribe to price updates for given asset IDs."""
        self._running = True
        self._subscribed_assets = set(asset_ids)

        while self._running:
            try:
                async with websockets.connect(self.WS_URL, ping_interval=30) as ws:
                    self._ws = ws
                    logger.info("ws_connected", url=self.WS_URL)

                    for asset_id in asset_ids:
                        subscribe_msg = {
                            "type": "market",
                            "assets_ids": [asset_id],
                        }
                        await ws.send(json.dumps(subscribe_msg))

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if self._on_price_update:
                                await self._on_price_update(data)
                        except json.JSONDecodeError:
                            logger.warning("ws_invalid_json", raw=str(message)[:200])

            except ConnectionClosed as e:
                logger.warning("ws_disconnected", code=e.code)
                if self._running:
                    await asyncio.sleep(5)
            except Exception as exc:
                logger.error("ws_error", error=str(exc))
                if self._running:
                    await asyncio.sleep(10)

    async def disconnect(self) -> None:
        """Disconnect gracefully."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("ws_disconnected_graceful")

    async def subscribe(self, asset_id: str) -> None:
        """Subscribe to a new asset while connected."""
        if self._ws and asset_id not in self._subscribed_assets:
            msg = {"type": "market", "assets_ids": [asset_id]}
            await self._ws.send(json.dumps(msg))
            self._subscribed_assets.add(asset_id)
