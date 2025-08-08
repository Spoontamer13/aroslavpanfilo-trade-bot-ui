import pytest
import numpy as np
from core.strategies.rsi import RSIStrategy

class DummyClient:
    def __init__(self):
        self.orders = []
    async def create_market_order(self, side, qty):
        self.orders.append((side, qty))

# Мокаем calculate_rsi, чтобы получать заранее известные значения
@pytest.fixture(autouse=True)
def patch_rsi(monkeypatch):
    def fake_rsi(prices, period):
        # вернём линейно растущий RSI
        arr = np.linspace(20, 80, len(prices))
        return arr
    monkeypatch.setattr("core.strategies.rsi.calculate_rsi", fake_rsi)

@pytest.mark.anyio
async def test_rsi_entry_and_tp_and_saldo():
    client = DummyClient()
    strat = RSIStrategy(client)

    # нарастающие цены дадут сначала закрепление, потом сигнал и вход
    # заполним close_prices вручную до сигнала
    for price in range(1, strat.rsi_period + 5):
        await strat.handle_candle({"open": price, "close": price})
    # После закрепления RSI < lower или > upper должны сформироваться позиции
    # Проверим, что хотя бы один ордер был
    assert client.orders, "Ожидается хотя бы один ордер"
    side, qty = client.orders[0]
    assert side in ("BUY", "SELL")

    # TP: поднимем цену до target
    entry_price = strat.positions[0]["price"]
    target = entry_price * (1 + strat.tp_percent/100 + strat.commission + strat.slippage)
    await strat.handle_candle({"open": target-1, "close": target+1})
    # позиция должна быть частично или полностью закрыта
    assert all(pos["qty"] < strat._calculate_qty(0) for pos in strat.positions)

    # Сальдо: сконструируем два pos как в simple
    strat.positions = [
        {"price": 100, "qty": 1, "side": "BUY"},
        {"price": 100, "qty": 1, "side": "BUY"},
    ]
    # earned=20, floating=-20 → True
    assert await strat._check_saldo(120) is True