"""
MACD Crossover Strategy

Buys when the MACD line crosses above the signal line.
Sells when the MACD line crosses below the signal line.
"""
import backtrader as bt


class MacdStrategy(bt.Strategy):
    params = dict(
        fast_period=12,
        slow_period=26,
        signal_period=9,
    )

    def __init__(self):
        self.macd = bt.ind.MACD(
            period_me1=self.p.fast_period,
            period_me2=self.p.slow_period,
            period_signal=self.p.signal_period,
        )
        self.crossover = bt.ind.CrossOver(self.macd.macd, self.macd.signal)

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
