import asyncio
from utils.binance_api import BinanceClient

async def test():
    client = BinanceClient()
    candle = await client.get_latest_candle()
    print("Последняя свеча:", candle)
    result = await client.create_market_order("buy", 0.001)
    print("Ордер:", result)
    await client.close()

asyncio.run(test())