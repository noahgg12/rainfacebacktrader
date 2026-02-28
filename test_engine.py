import backtrader as bt
import datetime
import os
import sys

# Simplified SMA Cross Strategy
class SmaCross(bt.SignalStrategy):
    params = dict(sma1=10, sma2=20)

    def __init__(self):
        sma1 = bt.ind.SMA(period=self.params.sma1)
        sma2 = bt.ind.SMA(period=self.params.sma2)
        crossover = bt.ind.CrossOver(sma1, sma2)
        self.signal_add(bt.SIGNAL_LONG, crossover)

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f'{bt.num2date(order.executed.dt)} BUY  EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
            else:
                print(f'{bt.num2date(order.executed.dt)} SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')

    def notify_trade(self, trade):
        if trade.isclosed:
            print(f'TRADE PROFIT: Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}')

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(10000.0)

    # Path to the data file
    datapath = '/Users/noah123/rainfacebacktrader/datas/orcl-1995-2014.txt'
    
    if not os.path.exists(datapath):
        print(f"Data file not found at {datapath}")
        sys.exit(1)

    # GenericCSVData for the format: Date,Open,High,Low,Close,Adj Close,Volume
    data = bt.feeds.GenericCSVData(
        dataname=datapath,
        fromdate=datetime.datetime(2000, 1, 1),
        todate=datetime.datetime(2000, 12, 31),
        nullvalue=0.0,
        dtformat='%Y-%m-%d',
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        adjclose=5,
        volume=6,
        openinterest=-1
    )

    cerebro.adddata(data)
    cerebro.addstrategy(SmaCross)
    cerebro.addsizer(bt.sizers.FixedSize, stake=100) # Increased stake for visibility

    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
