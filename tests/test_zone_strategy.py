import pytest
from core.strategies.zone import ZoneStrategy

class DummyClient:
    def __init__(self):
        self.orders = []
    async def create_market_order(self, side, qty):
        self.orders.append((side, qty))

@pytest.fixture(autouse=True)
def patch_mrc(monkeypatch):
    # повторно используем calculate_mrc_levels
    def fake_levels(prices):
        last = prices[-1]
        return {"3": last + 1, "2": last - 1}
    monkeypatch.setattr("core.strategies.zone.calculate_mrc_levels", fake_levels)

@pytest.mark.anyio
async def test_zone_entry_and_tp_and_saldo():
    client = DummyClient()
    strat = ZoneStrategy(client)

    # 30 свечей для заполнения levels
    for i in range(30):
        await strat.handle_candle({"open": 100, "close": 100 + i})
    # на уровне 2 вход
    strat.settings["zone"]["entry_zones"] = ["2"]
    strat.levels = {"2": 130.0}
    await strat.handle_candle({"open": 131, "close": 129})
    assert client.orders, "Ожидаем ордер при попадании в зону 2"