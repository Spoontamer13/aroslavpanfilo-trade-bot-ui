import pytest
from core.strategies.combo import ComboStrategy

class DummyClient:
    def __init__(self):
        self.orders = []
    async def create_market_order(self, side, qty):
        self.orders.append((side, qty))

@pytest.fixture(autouse=True)
def patch_all(monkeypatch):
    # RSI → BUY, MRC → BUY, Zone → BUY одновременно
    def fake_rsi(prices, period):
        return [10] * len(prices)  # всегда < threshold
    monkeypatch.setattr("core.strategies.combo.calculate_rsi", fake_rsi)

    def fake_mrc(prices):
        last = prices[-1]
        return {"2": last - 1}
    monkeypatch.setattr("core.strategies.combo.calculate_mrc_levels", fake_mrc)

@pytest.mark.anyio
async def test_combo_all_buy_signal():
    client = DummyClient()
    strat = ComboStrategy(client)

    # наполним close_prices
    for i in range(max(31, strat.rsi_period + 1)):
        await strat.handle_candle({"open": 100, "close": 100})
    # теперь уровень "2" и RSI дают BUY, Zone тоже
    strat.settings["zone"]["entry_zones"] = ["2"]
    # следующая свеча точно попадёт под все условия
    await strat.handle_candle({"open": 101, "close": 99})
    assert client.orders[0][0] == "BUY"
    assert strat.active is True