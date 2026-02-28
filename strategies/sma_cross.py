"""
SMA Crossover Strategy

Buys when the fast SMA crosses above the slow SMA.
Sells when the fast SMA crosses below the slow SMA.
"""
import backtrader as bt


class SmaCrossStrategy(bt.Strategy):
    params = dict(
        fast_period=10,
        slow_period=30,
    )

    def __init__(self):
        self.fast_sma = bt.ind.SMA(period=self.p.fast_period)
        self.slow_sma = bt.ind.SMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_sma, self.slow_sma)

        # Track orders so we don't send duplicates
        self.order = None

        # Trade log for the API
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
