"""
RSI Mean Reversion Strategy

Buys when RSI drops below the oversold level.
Sells when RSI rises above the overbought level.
"""
import backtrader as bt


class RsiStrategy(bt.Strategy):
    params = dict(
        rsi_period=14,
        oversold=30,
        overbought=70,
    )

    def __init__(self):
        self.rsi = bt.ind.RSI(period=self.p.rsi_period)

        # Track orders
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
            if self.rsi < self.p.oversold:
                self.order = self.buy()
        else:
            if self.rsi > self.p.overbought:
                self.order = self.sell()
