"""
EMA Crossover Strategy

Buys when the fast EMA crosses above the slow EMA.
Sells when the fast EMA crosses below the slow EMA.

Similar to SMA crossover but more responsive to recent price changes.
"""
import backtrader as bt


class EmaCrossStrategy(bt.Strategy):
    params = dict(
        fast_period=12,
        slow_period=26,
    )

    def __init__(self):
        self.fast_ema = bt.ind.EMA(period=self.p.fast_period)
        self.slow_ema = bt.ind.EMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_ema, self.slow_ema)

        self.order = None
        self.trade_log = []

    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.trade_log.append({
                "datetime": str(bt.num2date(order.executed.dt)),
                "type": "BUY" if order.isbuy() else "SELL",
                "price": round(order.executed.price, 4),
                "size": order.executed.size,
                "value": round(order.executed.value, 2),
                "commission": round(order.executed.comm, 4),
            })
        self.order = None

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            if self.crossover < 0:
                self.order = self.sell()
