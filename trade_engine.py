from __future__ import annotations

import logging
from typing import Optional


logger = logging.getLogger(__name__)


class BybitEngine:
    def __init__(self, api_key: str, api_secret: str, mode: str = "demo"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.mode = mode
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from pybit.unified_trading import HTTP

            self._client = HTTP(
                demo=self.mode == "demo",
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
        except Exception as exc:
            logger.warning("Bybit client not initialized: %s", exc)
            self._client = None

    def _not_ready(self) -> dict:
        return {"ok": False, "msg": "Bybit client is not available"}

    def get_price(self, symbol: str) -> Optional[float]:
        if not self._client:
            return None
        try:
            response = self._client.get_tickers(category="linear", symbol=symbol)
            if response.get("retCode") == 0 and response.get("result", {}).get("list"):
                return float(response["result"]["list"][0]["lastPrice"])
        except Exception as exc:
            logger.error("get_price(%s): %s", symbol, exc)
        return None

    def get_balance(self) -> dict:
        if not self._client:
            return self._not_ready()
        try:
            response = self._client.get_wallet_balance(accountType="UNIFIED")
            if response.get("retCode") != 0:
                return {"ok": False, "msg": response.get("retMsg", "Error")}
            account = response["result"]["list"][0]
            return {
                "ok": True,
                "equity": float(account.get("totalEquity", 0)),
                "available": float(account.get("totalAvailableBalance", 0)),
                "unrealisedPnl": float(account.get("totalPerpUPL", 0)),
            }
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    def get_positions(self, symbol: str = "") -> dict:
        if not self._client:
            return self._not_ready()
        try:
            params = {"category": "linear", "settleCoin": "USDT"}
            if symbol:
                params["symbol"] = symbol
            response = self._client.get_positions(**params)
            if response.get("retCode") != 0:
                return {"ok": False, "msg": response.get("retMsg", "Error")}
            positions = []
            for position in response.get("result", {}).get("list", []):
                size = float(position.get("size", 0))
                if size <= 0:
                    continue
                positions.append(
                    {
                        "symbol": position.get("symbol", ""),
                        "side": position.get("side", ""),
                        "size": size,
                        "entry": float(position.get("avgPrice", 0)),
                        "leverage": int(float(position.get("leverage", 1))),
                        "unrealisedPnl": float(position.get("unrealisedPnl", 0)),
                        "sl": float(position.get("stopLoss", 0)) or None,
                        "tp": float(position.get("takeProfit", 0)) or None,
                    }
                )
            return {"ok": True, "positions": positions}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        sl: float = 0.0,
        tp: float = 0.0,
        leverage: int = 20,
        order_type: str = "Market",
        price: float = 0.0,
    ) -> dict:
        if not self._client:
            return self._not_ready()
        try:
            try:
                self._client.set_leverage(
                    category="linear",
                    symbol=symbol,
                    buyLeverage=str(leverage),
                    sellLeverage=str(leverage),
                )
            except Exception:
                pass

            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "timeInForce": "GTC",
            }
            if order_type == "Limit" and price:
                params["price"] = str(price)
            if sl:
                params["stopLoss"] = str(sl)
            if tp:
                params["takeProfit"] = str(tp)

            response = self._client.place_order(**params)
            if response.get("retCode") == 0:
                return {"ok": True, "orderId": response.get("result", {}).get("orderId", ""), "msg": "Order placed"}
            return {"ok": False, "msg": response.get("retMsg", "Error")}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    def close_position(self, symbol: str) -> dict:
        if not self._client:
            return self._not_ready()
        data = self.get_positions(symbol)
        if not data.get("ok"):
            return data
        positions = data.get("positions", [])
        if not positions:
            return {"ok": False, "msg": f"No open position for {symbol}"}
        position = positions[0]
        close_side = "Sell" if position["side"] == "Buy" else "Buy"
        try:
            response = self._client.place_order(
                category="linear",
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=str(position["size"]),
                timeInForce="GTC",
                reduceOnly=True,
            )
            if response.get("retCode") == 0:
                return {"ok": True, "closed_pnl": 0.0, "msg": "Closed"}
            return {"ok": False, "msg": response.get("retMsg", "Error")}
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        if not self._client:
            return None
        try:
            response = self._client.get_tickers(category="linear", symbol=symbol)
            if response.get("retCode") == 0 and response.get("result", {}).get("list"):
                return float(response["result"]["list"][0].get("fundingRate", 0)) * 100
        except Exception as exc:
            logger.error("get_funding_rate(%s): %s", symbol, exc)
        return None

    def get_klines(self, symbol: str, interval: str = "240", limit: int = 100) -> list:
        """Получить свечи с Bybit."""
        try:
            resp = self._client.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if resp.get("retCode") == 0:
                raw = resp["result"]["list"]
                candles = []
                for r in reversed(raw):
                    candles.append({
                        "time":   int(r[0]),
                        "open":   float(r[1]),
                        "high":   float(r[2]),
                        "low":    float(r[3]),
                        "close":  float(r[4]),
                        "volume": float(r[5]),
                    })
                return candles
        except Exception as e:
            logger.warning(f"get_klines error: {e}")
        return []
