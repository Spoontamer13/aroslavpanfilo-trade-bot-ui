# utils/binance_api.py
import os
import time
import math
import hmac
import ssl
import hashlib
from urllib.parse import urlencode
from typing import Optional, Dict, Any

import aiohttp
import certifi
from aiohttp import (
    ClientConnectorCertificateError,
    ClientConnectorError,
    ServerTimeoutError,
)

from utils.logger import logger


class BinanceClient:
    """
    Лёгкий клиент для Binance USDT-M Futures (прод или тестнет).

    Важно для Windows/EXE:
    - Сессию создаём в init_session() с TCPConnector(ssl=<certifi SSL ctx>).
    - Никаких await в __init__.
    """

    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True, leverage: int = 10, hedge: bool = True):
    self.api_key = api_key
    self.api_secret = api_secret
    self.symbol = symbol
    self.base_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"

    self.leverage = int(leverage)
    self.hedge = bool(hedge)

    self.session = None
    self.step_size = None
    self.min_qty = None
    self.lot_step = None

    # ------------------ СЕТЕВАЯ ИНИЦИАЛИЗАЦИЯ ------------------

    async def init_session(self) -> None:
        from utils.logger import logger
        logger.info("[init_session] base_url=%s symbol=%s", self.base_url, self.symbol)
    
        # Закрыть старую сессию
        if self.session and not self.session.closed:
            try:
                await self.session.close()
            except Exception:
                pass
        self.session = None
    
        try:
            # SSL-контекст (важно для EXE/Windows)
            if os.getenv("TRADEBOT_SSL_OFF", "0") == "1":
                logger.warning("[init_session] SSL OFF (diagnostic)")
                connector = aiohttp.TCPConnector(ssl=False)
            else:
                cafile = certifi.where()
                logger.info("[init_session] certifi.where() = %s", cafile)
                ssl_ctx = ssl.create_default_context(cafile=cafile)
                connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    
            # 1) /time
            t = await self._request("GET", "/fapi/v1/time", {})
            if not t or "serverTime" not in t:
                raise RuntimeError("Не получили /fapi/v1/time от биржи")
            logger.info("[init_session] /time ok: %s", t.get("serverTime"))
    
            # 2) exchangeInfo → LOT_SIZE
            info = await self._request("GET", "/fapi/v1/exchangeInfo", {})
            if not info or "symbols" not in info:
                raise RuntimeError("exchangeInfo пустой/ошибочный")
            sym = next((s for s in info["symbols"] if s.get("symbol") == self.symbol), None)
            if not sym:
                raise RuntimeError(f"Символ {self.symbol} не найден в exchangeInfo")
    
            lot_flt = next((f for f in sym.get("filters", []) if f.get("filterType") == "LOT_SIZE"), None)
            if not lot_flt:
                raise RuntimeError("LOT_SIZE фильтр не найден")
            self.lot_step = float(lot_flt["stepSize"])
            logger.info("[init_session] lot_step=%.10f", self.lot_step)
    
            # Подтянуть step_size/min_qty через отдельный вызов (символьный exchangeInfo)
            await self._load_symbol_filters()
    
            # 3) режимы акаунта (не фатально, просто логируем ответ)
            try:
                await self._set_margin_mode("CROSSED")
                await self._set_hedge_mode(self.hedge)
                await self._set_leverage(self.leverage)  # ← ставим плечо на символ
            except Exception as e:
                logger.warning("[init_session] режимы не применены: %r", e)
    
            logger.info("[init_session] готово")
    
        except (ClientConnectorCertificateError, ClientConnectorError) as e:
            logger.error("[init_session][NETWORK] %r", e)
            raise
        except ServerTimeoutError as e:
            logger.error("[init_session][TIMEOUT] %r", e)
            raise
        except Exception as e:
            import traceback
            logger.error("[init_session][ERROR] %s\n%s", e, traceback.format_exc())
            raise

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""
        if self.session and not self.session.closed:
            await self.session.close()

    # ------------------ ПУБЛИЧНЫЕ МЕТОДЫ ------------------
    async def _set_leverage(self, leverage: int):
        from utils.logger import logger
        params = {"symbol": self.symbol, "leverage": int(leverage)}
        res = await self._signed_request("POST", "/fapi/v1/leverage", params)
        logger.info("[API] leverage set → %s", res)
        return res
    async def _ticker_price(self) -> float | None:
        data = await self._request("GET", "/fapi/v1/ticker/price", {"symbol": self.symbol})
        if data and "price" in data:
            try:
                return float(data["price"])
            except Exception:
                return None
        return None
    async def get_available_balance(self) -> float:
        # /fapi/v2/account → availableBalance
        data = await self._signed_request("GET", "/fapi/v2/account", {})
        if not data:
            return 0.0
        try:
            return float(data.get("availableBalance", 0.0))
        except Exception:
            return 0.0
    

    async def exchange_time(self) -> Optional[int]:
        """Простой REST-пинг — время сервера."""
        data = await self._request("GET", "/fapi/v1/time", {})
        if data and "serverTime" in data:
            return int(data["serverTime"])
        return None

    async def get_latest_candle(self) -> Optional[Dict[str, float]]:
        """Последняя 1-минутная свеча (open/close)."""
        data = await self._request("GET", "/fapi/v1/klines", {
            "symbol": self.symbol, "interval": "1m", "limit": 1
        })
        if not data:
            return None
        try:
            open_p = float(data[0][1])
            close_p = float(data[0][4])
            return {"open": open_p, "close": close_p}
        except Exception as e:
            logger.error("[API] Ошибка парсинга kline: %r -> %s", e, data)
            return None

    async def get_balance(self) -> float:
        """Баланс USDT по /fapi/v2/balance."""
        data = await self._signed_request("GET", "/fapi/v2/balance", {})
        if not data:
            return 0.0
        for entry in data:
            if entry.get("asset") == "USDT":
                try:
                    return float(entry.get("balance", 0.0))
                except Exception:
                    return 0.0
        return 0.0

    async def order(self, side: str, qty: float):
        from utils.logger import logger
    
        # 1) Текущая цена
        price = await self._ticker_price()
        if not price:
            logger.error("[API] Нет цены для %s — отмена ордера", self.symbol)
            return None
    
        # 2) Доступная маржа
        avail = await self.get_available_balance()
        max_notional = avail * float(self.leverage)
    
        # 3) Желаемая нотация и ограничение по марже
        want_notional = qty * price
        if want_notional > max_notional and max_notional > 0:
            max_qty = max_notional / price
            logger.warning(
                "[RISK] Margin cap: avail=%.4f, lev=%s, price=%.2f -> qty %.6f → %.6f",
                avail, self.leverage, price, qty, max_qty
            )
            qty = max_qty
    
        # 4) Округление под LOT_SIZE
        qty = self._round_qty(qty)
        if qty <= 0:
            logger.error("[API] Отказ: расчётный qty=%.10f ≤ 0 после округления", qty)
            return None
    
        logger.info(
            "[CHK] availBalance=%.4f, leverage=%s, price=%.2f, request qty=%.6f (notional≈%.2f)",
            avail, self.leverage, price, qty, qty * price
        )
    
        params = {
            "symbol": self.symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty,
        }
        # 5) Hedge-mode → positionSide
        if self.hedge:
            params["positionSide"] = "LONG" if side.upper() == "BUY" else "SHORT"
    
        resp = await self._signed_request("POST", "/fapi/v1/order", params)
        logger.info("[API → New order] side=%s, qty=%.6f → %s", side, qty, resp)
        return resp

    # ------------------ ВСПОМОГАТЕЛЬНЫЕ/ПРИВАТНЫЕ ------------------

    async def _load_symbol_filters(self) -> None:
        """Подтягиваем step_size/min_qty для округления количества."""
        data = await self._request("GET", "/fapi/v1/exchangeInfo", {"symbol": self.symbol})
        if not data:
            logger.error("[API] exchangeInfo пуст для %s", self.symbol)
            return

        for s in data.get("symbols", []):
            if s.get("symbol") == self.symbol:
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        try:
                            self.step_size = float(f["stepSize"])
                            self.min_qty = float(f["minQty"])
                            logger.info(
                                "[API] LOT_SIZE %s: step=%s, min=%s",
                                self.symbol, self.step_size, self.min_qty
                            )
                        except Exception as e:
                            logger.error("[API] Ошибка парсинга LOT_SIZE: %r", e)
                        return
        logger.error("[API] Не удалось найти LOT_SIZE для %s", self.symbol)

    def _round_qty(self, qty: float) -> float:
        """Округление количества под шаг/минимум биржи."""
        if self.step_size is None or self.min_qty is None:
            return qty
        q = math.floor(qty / self.step_size) * self.step_size
        if q < self.min_qty:
            q = self.min_qty
        return q

    def round_qty(self, qty: float) -> float:
        """Округление по lot_step, если нужно где-то снаружи."""
        step = self.lot_step or self.step_size or 0.0
        if step <= 0:
            return qty
        return math.floor(qty / step) * step

    async def _set_margin_mode(self, mode: str) -> None:
        res = await self._signed_request("POST", "/fapi/v1/marginType", {
            "symbol": self.symbol, "marginType": mode
        })
        logger.info("[API] marginType set → %s", res)

    async def _set_hedge_mode(self, dual: bool) -> None:
        res = await self._signed_request("POST", "/fapi/v1/positionSide/dual", {
            "dualSidePosition": str(dual).lower()
        })
        logger.info("[API] hedge-mode set → %s", res)

    async def _request(self, method: str, path: str, params: dict) -> Optional[Dict[str, Any]]:
        """Общий публичный запрос."""
        if not self.session:
            logger.error("[API] session is None (init_session не вызывали?)")
            return None

        url = self.base_url + path
        try:
            async with self.session.request(method, url, params=params) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error("[API] %s %s %s -> %s", method, path, params, text)
                    return None
                try:
                    return await resp.json()
                except Exception:
                    logger.error("[API] JSON parse error: %s", text)
                    return None
        except Exception as e:
            logger.error("[API] request exception %s %s: %r", method, url, e)
            return None

    async def _signed_request(self, method: str, path: str, params: dict) -> Optional[Dict[str, Any]]:
        """Подписанный запрос для приватных эндпоинтов."""
        if not self.session:
            logger.error("[API] session is None (init_session не вызывали?)")
            return None

        params = dict(params) if params else {}
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000

        query_string = urlencode(sorted(params.items()), doseq=True)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        url = f"{self.base_url}{path}?{query_string}&signature={signature}"
        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with self.session.request(method, url, headers=headers) as resp:
                txt = await resp.text()
                if resp.status != 200:
                    logger.error("[API] Signed request failed (%s): %s", resp.status, txt)
                    return None
                try:
                    return await resp.json()
                except Exception:
                    logger.error("[API] Failed to parse JSON: %s", txt)
                    return None
        except Exception as e:
            logger.error("[API] Signed request error %s %s: %r", method, path, e)
            return None

    # ------------------ ПРОСТАЯ ВАЛИДАЦИЯ КЛЮЧЕЙ ------------------

    def _validate_keys(self) -> None:
        # Это не гарантия валидности на стороне биржи, просто дружелюбные подсказки
        if not self.api_key or len(self.api_key) < 10:
            logger.warning("[API KEY] Ключ пустой/слишком короткий — проверяй settings.yaml")
        if not self.api_secret or len(self.api_secret) < 10:
            logger.warning("[API SECRET] Секрет пустой/слишком короткий — проверяй settings.yaml")
