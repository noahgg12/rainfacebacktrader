"""
Bollinger Bands Mean Reversion Strategy

Buys when price closes below the lower Bollinger Band (oversold).
Sells when price closes above the upper Bollinger Band (overbought).
"""
import backtrader as bt


class BollingerStrategy(bt.Strategy):
    params = dict(
        period=20,
        devfactor=2.0,
    )

    def __init__(self):
        self.boll = bt.ind.BollingerBands(
            period=self.p.period,
            devfactor=self.p.devfactor,
        )

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
            if self.data.close[0] < self.boll.lines.bot[0]:
                self.order = self.buy()
        else:
            if self.data.close[0] > self.boll.lines.top[0]:
                self.order = self.sell()
