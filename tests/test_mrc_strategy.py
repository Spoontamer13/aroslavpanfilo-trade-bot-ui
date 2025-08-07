import pytest
from core.strategies.mrc import MRCStrategy

class DummyClient:
    def __init__(self):
        self.orders = []
    async def create_market_order(self, side, qty):
        self.orders.append((side, qty))

@pytest.fixture(autouse=True)
def patch_mrc(monkeypatch):
    # выдаём жёстко заданные уровни
    def fake_levels(prices):
        # пусть уровни "3" и "2.1" будут около последней цены
        last = prices[-1]
        return {"3": last + 1, "2.1": last - 1}
    monkeypatch.setattr("core.strategies.mrc.calculate_mrc_levels", fake_levels)

@pytest.mark.anyio
async def test_mrc_entry_and_tp_and_saldo():
    client = DummyClient()
    strat = MRCStrategy(client)

    # первая свеча (len < 30) ничего не делает
    for i in range(29):
        await strat.handle_candle({"open": 100 + i, "close": 100 + i})
    # 30-я свеча — должны заполниться уровни, но без входа
    await strat.handle_candle({"open": 130, "close": 130})
    assert not client.orders

    # 31-я свеча на уровне entry_level
    strat.settings["mrc"]["entry_level"] = "2.1"
    prices = [i for i in range(100, 130)]
    # вручную инициируем levels
    strat.levels = {"2.1": 130.0}
    await strat.handle_candle({"open": 131, "close": 129})
    assert client.orders, "Ожидаем ордер при пересечении 2.1"