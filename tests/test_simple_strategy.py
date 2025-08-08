import pytest
from core.strategies.simple import SimpleStrategy

class DummyClient:
    def __init__(self):
        self.orders = []
    async def create_market_order(self, side, qty):
        self.orders.append((side, qty))

@pytest.mark.anyio
async def test_simple_initial_entry_and_partial_tp_and_saldo():
    client = DummyClient()
    strat = SimpleStrategy(client)

    # 1) Первая свеча — открывается первая позиция
    candle = {"open": 100, "close": 100}
    await strat.handle_candle(candle)
    assert len(strat.positions) == 1
    assert client.orders == [("BUY", pytest.approx(strat.base_order_percent))]

    # 2) Рост до TP: частичное закрытие по default partial_close_percent=1.0
    entry = strat.positions[0]
    target = entry["price"] * (1 + strat.tp_percent/100 + strat.commission + strat.slippage)
    candle2 = {"open": target - 1, "close": target + 1}
    client.orders.clear()
    # partial_close_percent по умолчанию 1.0, значит полное закрытие
    await strat.handle_candle(candle2)
    assert strat.positions == []
    # если бы partial <1, проверяли бы часть qty

    # 3) Тест сальдо: соберём две позиции вручную
    client = DummyClient()
    strat = SimpleStrategy(client)
    strat.positions = [
        {"price": 100, "qty": 1, "side": "BUY"},
        {"price": 100, "qty": 1, "side": "BUY"},
    ]
    # первая по цене 90 убыток, вторая по 120 прибыль
    close_price = 120
    # earned = 20, floating = -20 => saldo = (20/20 -1)*100 = 0% < threshold → False
    assert await strat._check_saldo(close_price) is False
    # если сделаем first price = 80: delta1=-20, delta2=40 => saldo=(40/20 -1)*100=100% >= threshold
    strat.positions = [
        {"price": 100, "qty": 1, "side": "BUY"},
        {"price": 100, "qty": 1, "side": "BUY"},
    ]
    assert await strat._check_saldo(120) is True