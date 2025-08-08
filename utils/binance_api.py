
import math
import site
import time
import hmac
import hashlib
from urllib.parse import urlencode
import os, ssl, certifi

# чтобы requests/aiohttp/вебсокеты видели корневые сертификаты
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

import aiohttp
from numpy import quantile
from utils.logger import logger


class BinanceClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
        
        testnet: bool = True
    ):
        self.api_key    = api_key
        self.api_secret = api_secret
        self.symbol     = symbol
        
        self.session    = None
        self.base_url   = "https://testnet.binancefuture.com"
       
        self.step_size = None
        self.min_qty   = None

    async def init_session(self):
        self.session = aiohttp.ClientSession()
        info = await self._request("GET", "/fapi/v1/exchangeInfo", {})
        sym = next(s for s in info["symbols"] if s["symbol"] == self.symbol)
        lot_flt = next(f for f in sym["filters"] if f["filterType"]=="LOT_SIZE")
        self.lot_step = float(lot_flt["stepSize"])
       
        await self._load_symbol_filters()
       
        await self._set_margin_mode("CROSSED")
        await self._set_hedge_mode(True)
        await session.ws_connect(url, ssl=SSL_CTX, ...)

    async def _load_symbol_filters(self):
       
        path = "/fapi/v1/exchangeInfo"
        url = self.base_url + path
        async with self.session.get(url, params={"symbol": self.symbol}) as resp:
            data = await resp.json()
            for s in data.get("symbols", []):
                if s["symbol"] == self.symbol:
                    for f in s["filters"]:
                        if f["filterType"] == "LOT_SIZE":
                            self.step_size = float(f["stepSize"])
                            self.min_qty   = float(f["minQty"])
                            return
        logger.error(f"[API] Не удалось получить фильтры LOT_SIZE для {self.symbol}")

    def _round_qty(self, qty: float) -> float:
        
        if self.step_size is None or self.min_qty is None:
            return qty
        
        q = math.floor(qty / self.step_size) * self.step_size
        if q < self.min_qty:
            q = self.min_qty
        return q

    async def order(self, side: str, qty: float):
       

        
        qty = self._round_qty(qty)
        if qty <= 0:
            logger.error(f"[API] Отказ: расчётный qty={qty} ≤ 0 после округления")
            return None

        path   = "/fapi/v1/order"
        params = {
            "symbol":   self.symbol,
            "side":     side.upper(),
            "type":     "MARKET",
            "quantity": qty,
        }
        resp = await self._signed_request("POST", path, params)
        logger.info(f"[API → New order] side={side}, qty={qty:.6f} → {resp}")
        return resp


    async def close(self):
        if self.session:
            await self.session.close()

    async def _set_margin_mode(self, mode: str):
        path   = "/fapi/v1/marginType"
        params = {"symbol": self.symbol, "marginType": mode}
        res = await self._signed_request("POST", path, params)
        logger.info(f"[API] marginType set → {res}")

    async def _set_hedge_mode(self, dual: bool):
        path   = "/fapi/v1/positionSide/dual"
        params = {"dualSidePosition": str(dual).lower()}
        res = await self._signed_request("POST", path, params)
        logger.info(f"[API] hedge-mode set → {res}")

    async def get_latest_candle(self) -> dict | None:
       
        path   = "/fapi/v1/klines"
        params = {"symbol": self.symbol, "interval": "1m", "limit": 1}
        data = await self._request("GET", path, params)
        if not data or len(data) == 0:
            return None
        
        open_p  = float(data[0][1])
        close_p = float(data[0][4])
        return {"open": open_p, "close": close_p}

   
    async def _request(self, method: str, path: str, params: dict):
        url = self.base_url + path
        async with self.session.request(method, url, params=params) as resp:
            text = await resp.text()
            try:
                return await resp.json()
            except Exception:
                logger.error(f"[API] Error parsing JSON: {text}")
                return None

    async def close(self):
        
        await self.session.close()

    def _timestamp(self) -> int:
       
        return int(time.time() * 1000)

    async def get_balance(self) -> float:
        
        path = "/fapi/v2/balance"
        data = await self._signed_request("GET", path, {})
        if not data:
            return 0.0
       
        for entry in data:
            if entry.get("asset") == "USDT":
                
                return float(entry.get("balance", 0.0))
        return 0.0
    def round_qty(self, qty: float) -> float:
       
        step = self.lot_step  
        return math.floor(qty / step) * step
    async def _signed_request(self, method: str, path: str, params: dict):
       
        params["timestamp"] = int(time.time() * 1000)
       
        params["recvWindow"] = 5000

       
        query_string = urlencode(sorted(params.items()), doseq=True)

      
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

      
        url = f"{self.base_url}{path}?{query_string}&signature={signature}"

        headers = {
            "X-MBX-APIKEY": self.api_key
        }

       
        async with self.session.request(method, url, headers=headers) as resp:
            text = await resp.text()
            if resp.status != 200:
                logger.error(f"[API] Signed request failed ({resp.status}): {text}")
                return None
            try:
                return await resp.json()
            except Exception:
                logger.error(f"[API] Failed to parse JSON: {text}")
                return None
