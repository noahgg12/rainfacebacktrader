"""
Stochastic Oscillator Strategy

Buys when %K crosses above %D while both are in the oversold zone.
Sells when %K crosses below %D while both are in the overbought zone.
"""
import backtrader as bt


class StochasticStrategy(bt.Strategy):
    params = dict(
        k_period=14,
        d_period=3,
        oversold=20,
        overbought=80,
    )

    def __init__(self):
        self.stoch = bt.ind.Stochastic(
            period=self.p.k_period,
            period_dfast=self.p.d_period,
        )
        self.crossover = bt.ind.CrossOver(self.stoch.percK, self.stoch.percD)

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
            if (self.crossover > 0
                    and self.stoch.percK[0] < self.p.oversold):
                self.order = self.buy()
        else:
            if (self.crossover < 0
                    and self.stoch.percK[0] > self.p.overbought):
                self.order = self.sell()
