# utils/binance_api.py
import os
import time
import math
import hmac
import ssl
import hashlib
from urllib.parse import urlencode


import aiohttp
import certifi
from aiohttp import ClientConnectorCertificateError, ClientConnectorError, ServerTimeoutError
from utils.logger import logger


def _ssl_context() -> ssl.SSLContext:
    """
    Единый SSL-контекст с корнями certifi.
    Критично для PyInstaller EXE на Windows (иначе SSL: CERTIFICATE_VERIFY_FAILED).
    """
    cafile = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", cafile)

    ctx = ssl.create_default_context(cafile=cafile)
    # Если где-то понадобится, можно ослабить:
    # ctx.check_hostname = True
    # ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


class BinanceClient:
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

        # База для USDT-M Futures
        # Прод: https://fapi.binance.com
        # Тестнет: https://testnet.binancefuture.com
        self.base_url = (
            "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
        )

        self.session: aiohttp.ClientSession | None = None
        self._ssl = _ssl_context()

        self.step_size: float | None = None
        self.min_qty: float | None = None
        self.lot_step: float | None = None

    async def init_session(self):
        """
        Создаём сессию с явным SSL-контекстом (certifi). На Windows-EXE это MUST HAVE.
        Логируем каждый шаг. Если включена переменная окружения TRADEBOT_SSL_OFF=1,
        создаём TCPConnector(ssl=False) — только для диагностики.
        """
        logger.info("[init_session] base_url=%s symbol=%s", self.base_url, self.symbol)

        try:
            ssl_ctx = None
            if os.getenv("TRADEBOT_SSL_OFF", "0") == "1":
                logger.warning("[init_session] SSL OFF (диагностика): TCPConnector(ssl=False)")
                connector = aiohttp.TCPConnector(ssl=False)
            else:
                cafile = certifi.where()
                logger.info("[init_session] certifi.where() = %s", cafile)
                ssl_ctx = ssl.create_default_context(cafile=cafile)
                connector = aiohttp.TCPConnector(ssl=ssl_ctx)

            timeout = aiohttp.ClientTimeout(total=20)
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

            # 1) элементарный пинг времени (REST)
            t = await self._request("GET", "/fapi/v1/time", {})
            if not t:
                raise RuntimeError("Не получили time от биржи")
            logger.info("[init_session] /time ok: %s", t)

            # 2) exchangeInfo (требуется дальше)
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

            # режимы
            await self._set_margin_mode("CROSSED")
            await self._set_hedge_mode(True)

            logger.info("[init_session] готово")

        except (ClientConnectorCertificateError, ClientConnectorError) as e:
            logger.error("[init_session][NETWORK] %s", repr(e))
            logger.error("Возможные причины: корпоративный прокси/антивирус перехватывает SSL,"
                         " кривые корневые сертификаты Windows, или недоступен testnet.")
            raise
        except ServerTimeoutError as e:
            logger.error("[init_session][TIMEOUT] %s", repr(e))
            raise
        except Exception as e:
            # Логируем полный трейс — пусть в UI отобразится
            import traceback
            logger.error("[init_session][ERROR] %s\n%s", e, traceback.format_exc())
            raise

    async def exchange_time(self) -> int | None:
        """Простой REST-пинг сервера. Возвращает serverTime в мс."""
        data = await self._request("GET", "/fapi/v1/time", {})
        if data and "serverTime" in data:
            return int(data["serverTime"])
        return None

    async def _load_symbol_filters(self):
        """Подтягиваем step_size/min_qty для округления количества."""
        data = await self._request("GET", "/fapi/v1/exchangeInfo", {"symbol": self.symbol})
        if not data:
            logger.error(f"[API] exchangeInfo пуст для {self.symbol}")
            return

        for s in data.get("symbols", []):
            if s.get("symbol") == self.symbol:
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        try:
                            self.step_size = float(f["stepSize"])
                            self.min_qty = float(f["minQty"])
                            logger.info(
                                f"[API] LOT_SIZE {self.symbol}: step={self.step_size}, min={self.min_qty}"
                            )
                        except Exception as e:
                            logger.error(f"[API] Ошибка парсинга LOT_SIZE: {e}")
                        return
        logger.error(f"[API] Не удалось найти LOT_SIZE для {self.symbol}")

    # ---------- Вспомогательные округления ----------
    def _round_qty(self, qty: float) -> float:
        if self.step_size is None or self.min_qty is None:
            return qty
        q = math.floor(qty / self.step_size) * self.step_size
        if q < self.min_qty:
            q = self.min_qty
        return q

    def round_qty(self, qty: float) -> float:
        """Округление по lot_step (если используешь где-то снаружи)."""
        step = self.lot_step or self.step_size or 0.0
        if step <= 0:
            return qty
        return math.floor(qty / step) * step

    # ---------- Публичные методы ----------
    async def get_latest_candle(self) -> dict | None:
        """Последняя 1-минутная свеча."""
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
            logger.error(f"[API] Ошибка парсинга kline: {e} -> {data}")
            return None

    async def get_balance(self) -> float:
        """Возвращает баланс USDT."""
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
        """Маркет-ордер с округлением количества под фильтры."""
        qty = self._round_qty(qty)
        if qty <= 0:
            logger.error(f"[API] Отказ: расчётный qty={qty} ≤ 0 после округления")
            return None

        params = {
            "symbol": self.symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty,
        }
        resp = await self._signed_request("POST", "/fapi/v1/order", params)
        logger.info(f"[API → New order] side={side}, qty={qty:.6f} → {resp}")
        return resp

    async def close(self):
        """Закрываем сессию."""
        if self.session and not self.session.closed:
            await self.session.close()

    # ---------- Приватные вызовы/утилы ----------
    async def _set_margin_mode(self, mode: str):
        res = await self._signed_request("POST", "/fapi/v1/marginType", {
            "symbol": self.symbol, "marginType": mode
        })
        logger.info(f"[API] marginType set → {res}")

    async def _set_hedge_mode(self, dual: bool):
        res = await self._signed_request("POST", "/fapi/v1/positionSide/dual", {
            "dualSidePosition": str(dual).lower()
        })
        logger.info(f"[API] hedge-mode set → {res}")

    async def _request(self, method: str, path: str, params: dict):
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

    async def _signed_request(self, method: str, path: str, params: dict):
        """Подписанный запрос для приватных эндпоинтов."""
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
                    logger.error(f"[API] Signed request failed ({resp.status}): {txt}")
                    return None
                try:
                    return await resp.json()
                except Exception:
                    logger.error(f"[API] Failed to parse JSON: {txt}")
                    return None
        except Exception as e:
            logger.error(f"[API] Signed request error {method} {path}: {e}")
            return None
