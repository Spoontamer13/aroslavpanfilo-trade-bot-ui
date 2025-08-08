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

    ВАЖНО для Windows/EXE:
    - Сессия создаётся в init_session() с TCPConnector(ssl=SSLCTX),
      где SSLCTX построен на основе certifi.
    - Никаких await на уровне модуля и в __init__.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
        testnet: bool = True,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol

        # Прод: https://fapi.binance.com
        # Тестнет: https://testnet.binancefuture.com
        self.base_url = (
            "https://testnet.binancefuture.com" 
        )

        self.session: Optional[aiohttp.ClientSession] = None

        # Торговые фильтры
        self.step_size: Optional[float] = None
        self.min_qty: Optional[float] = None
        self.lot_step: Optional[float] = None

    # ------------------ СЕТЕВАЯ ИНИЦИАЛИЗАЦИЯ ------------------

    async def init_session(self) -> None:
        """
        Создаёт aiohttp-сессию с корректными корневыми сертификатами (certifi).
        Делает базовые запросы (time, exchangeInfo) и настраивает режимы.
        """
        logger.info("[init_session] base_url=%s symbol=%s", self.base_url, self.symbol)

        # Закроем предыдущую сессию, если вдруг есть
        if self.session and not self.session.closed:
            try:
                await self.session.close()
            except Exception:
                pass
        self.session = None

        try:
            # Диагностический переключатель: можно отключить SSL проверку
            if os.getenv("TRADEBOT_SSL_OFF", "0") == "1":
                logger.warning("[init_session] SSL OFF (diagnostic): TCPConnector(ssl=False)")
                connector = aiohttp.TCPConnector(ssl=False)
            else:
                cafile = certifi.where()
                logger.info("[init_session] certifi.where() = %s", cafile)
                ssl_ctx = ssl.create_default_context(cafile=cafile)
                connector = aiohttp.TCPConnector(ssl=ssl_ctx)

            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

            # 1) здравствуй, сеть
            t = await self.exchange_time()
            if not t:
                raise RuntimeError("Не получили /fapi/v1/time от биржи")
            logger.info("[init_session] /time ok: %s", t)

            # 2) exchangeInfo (нужен для фильтров)
            info = await self._request("GET", "/fapi/v1/exchangeInfo", {})
            if not info or "symbols" not in info:
                raise RuntimeError("exchangeInfo пустой/ошибочный")

            sym = next((s for s in info["symbols"] if s.get("symbol") == self.symbol), None)
            if not sym:
                raise RuntimeError(f"Символ {self.symbol} не найден в exchangeInfo")

            lot_flt = next((f for f in sym["filters"] if f.get("filterType") == "LOT_SIZE"), None)
            if not lot_flt:
                raise RuntimeError("LOT_SIZE фильтр не найден")
            self.lot_step = float(lot_flt["stepSize"])
            logger.info("[init_session] lot_step=%.10f", self.lot_step)

            await self._load_symbol_filters()

            # Режимы аккаунта (не фатально, просто логируем)
            try:
                await self._set_margin_mode("CROSSED")
                await self._set_hedge_mode(True)
            except Exception as e:
                logger.warning("[init_session] режимы не применены: %r", e)

            logger.info("[init_session] готово")

        except (ClientConnectorCertificateError, ClientConnectorError) as e:
            logger.error("[init_session][NETWORK] %r", e)
            logger.error(
                "Причины: корпоративный прокси/антивирус перехватывает SSL, "
                "кривые корневые сертификаты Windows, или недоступен testnet."
            )
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

    async def order(self, side: str, qty: float) -> Optional[Dict[str, Any]]:
        """Маркет-ордер. Кол-во округляется под фильтры."""
        qty = self._round_qty(qty)
        if qty <= 0:
            logger.error("[API] Отказ: расчётный qty=%s ≤ 0 после округления", qty)
            return None

        params = {
            "symbol": self.symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty,
        }
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
