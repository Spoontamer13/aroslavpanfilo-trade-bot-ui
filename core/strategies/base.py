import logging

logger = logging.getLogger(__name__)
logger.propagate = True 

class BaseStrategy:
    def __init__(self, client, settings):
        self.client = client
        self.settings = settings.get('global', {})
        self.positions = []  # list of dicts: price, qty, side
        # global parameters
        g = self.settings
        self.leverage = g.get('leverage', 10)
        self.trade_direction = self.settings.get("trade_direction", "BOTH").upper()
        self.base_order_percent = g.get('base_order_percent', 1.0)/ 100.0
        self.step_percent = g.get('step_percent', 0.4)
        self.step_multiplier = g.get('step_multiplier', 1.0)
        self.min_step_percent = g.get('min_step_percent', 0.2)
        self.tp_percent = g.get('tp_percent', 0.8) / 100.0
        self.saldo_threshold = g.get('saldo_threshold_percent', 30.0)
        self.partial_close_percent = g.get('partial_close_percent', 100.0) / 100.0
        self.commission = g.get('commission_percent', 0.04) / 100.0
        self.slippage = g.get('slippage_percent', 0.05) / 100.0
        self.max_orders = g.get('max_orders', None)
        # Averaging mode: 'martingale', 'pyramiding', or 'mirror'
        self.avg_mode = g.get('avg_mode', 'martingale')
        # Separate multiplier for lot sizing
        self.lot_multiplier = g.get('lot_multiplier', 1.0)
        # Level index for pyramiding/mirror modes
        self.level = 0
        self.account_balance = None
        self.active = False

    async def handle_candle(self, candle: dict):
        price = candle['close']
        # при первом входе — забираем баланс один раз
        if self.account_balance is None:
            self.account_balance = await self.client.get_balance()
            logger.info(f"[{self.__class__.__name__}] Баланс USDT: {self.account_balance:.2f}")

        # entry
        if not self.active:
            signal = self._signal(price, candle)
            if signal:
                await self._open(position_price=price, side=signal)
                self.active = True
            return

        # дальше TP / усреднение…
        await self._check_tp_and_saldo(price)
        if self._can_avg(price):
            await self._open_avg(price)

    def _signal(self, price, candle):
        # Override in subclass
        return None

    async def _open(self, position_price, side):
        qty = self._calculate_qty(position_price, first=True)
        self.positions.append({'price': position_price, 'qty': qty, 'side': side})
        await self.client.order(side, qty)

    async def _open_avg(self, price):
        side = self.positions[0]['side']
        qty = await self._calculate_qty(price)
        self.positions.append({'price': price, 'qty': qty, 'side': side})
        logger.info(f"[{self.__class__.__name__}] Усредняемся {side}: qty={qty:.6f} @ {price:.2f}")
        await self.client.order(side, qty)
        self._update_level_on_avg()

    def _calculate_qty(self, price: float, first: bool = False) -> float:
        """
        Если first==True, считаем от баланса:
          qty = (balance * base_order_percent * leverage) / price
        Иначе — по усреднению:
          qty = previous_qty * lot_multiplier
        """
        if first:
            alloc = self.account_balance * self.base_order_percent * self.leverage
            return alloc / price if price > 0 else 0.0
        else:
            # пример для мартингейла
            last_qty = self.positions[-1]['qty']
            return last_qty * (self.settings.get('lot_multiplier', 1.0))

    def _can_avg(self, price):
        if self.max_orders and len(self.positions) >= self.max_orders:
            return False
        last_price = self.positions[-1]['price']
        if self.avg_mode == 'martingale':
            idx = len(self.positions)
        else:
            idx = self.level
        step = self.step_percent * (self.step_multiplier ** idx)
        target_step = max(step, self.min_step_percent)
        delta = abs(price - last_price) / last_price * 100.0
        return delta >= target_step

    def _update_level_on_avg(self):
        if self.avg_mode == 'mirror':
            self.level += 1
        elif self.avg_mode == 'pyramiding':
            self.level = max(self.level - 1, 0)
        # Martingale: level unchanged

    def _update_level_on_tp(self):
        if self.avg_mode == 'pyramiding':
            self.level += 1
        elif self.avg_mode == 'mirror':
            self.level = max(self.level - 1, 0)
        # Martingale: level unchanged

    async def _check_tp_and_saldo(self, price):
        # Individual TP logic
        for pos in list(self.positions):
            entry = pos['price']
            qty = pos['qty']
            side = pos['side']
            if side == 'BUY':
                # Compute TP target including slippage & commission
                target = entry * (1 + self.tp_percent)
                target *= (1 + self.slippage) * (1 + self.commission)
                if price >= target:
                    close_qty = qty * self.partial_close_percent
                    logger.info(f"[{self.__class__.__name__}] Закрываем по TP {side}: qty={close_qty:.6f} @ {price:.2f}")
                    await self.client.order('SELL', close_qty)
                    self._update_level_on_tp()
                    if self.partial_close_percent >= 1.0:
                        self.positions.remove(pos)
                    else:
                        pos['qty'] = qty - close_qty
            else:
                target = entry * (1 - self.tp_percent)
                target *= (1 - self.slippage) * (1 - self.commission)
                if price <= target:
                    close_qty = qty * self.partial_close_percent
                    logger.info(f"[{self.__class__.__name__}] Закрываем по TP {side}: qty={close_qty:.6f} @ {price:.2f}")
                    await self.client.order('BUY', close_qty)
                    self._update_level_on_tp()
                    if self.partial_close_percent >= 1.0:
                        self.positions.remove(pos)
                    else:
                        pos['qty'] = qty - close_qty

        if not self.positions:
            self.active = False
        # Saldo check
        if await self._check_saldo(price):
            logger.info(f"[{self.__class__.__name__}] Сальдо достигло порога — закрываем все позиции")
            for pos in list(self.positions):
                close_side = 'SELL' if pos['side'] == 'BUY' else 'BUY'
                logger.info(f"[{self.__class__.__name__}] Закрываем {close_side}: qty={pos['qty']:.6f} @ {price:.2f}")
                await self.client.order(close_side, pos['qty'])
            self.positions.clear()
            self.active = False
            # Reset level at cycle end
            self.level = 0

    async def _check_saldo(self, price):
        earned = 0.0
        floating = 0.0
        closed_any = False
        for pos in self.positions:
            entry = pos['price']
            qty = pos['qty']
            if pos['side'] == 'BUY':
                exit_net = price * (1 - self.commission) * (1 - self.slippage)
                entry_net = entry * (1 + self.commission) * (1 + self.slippage)
                pnl = (exit_net - entry_net) * qty
            else:
                entry_net = entry * (1 - self.commission) * (1 - self.slippage)
                exit_net = price * (1 + self.commission) * (1 + self.slippage)
                pnl = (entry_net - exit_net) * qty
            if pnl >= 0:
                earned += pnl
            else:
                floating += pnl
        if earned <= 0 or floating >= 0:
            return False
        saldo = (earned / abs(floating) - 1) * 100.0
        return saldo >= self.saldo_threshold
