"""
Rainface Backtrader Sandbox Runner

Runs inside an isolated Docker container. Reads a JSON job from stdin,
executes the custom strategy backtest, writes JSON results to stdout.

This file is the ENTRYPOINT of the sandbox container.
Since the container runs with --network=none and --read-only, the
untrusted custom strategy code cannot exfiltrate data or modify the host.
"""
import csv
import datetime
import io
import json
import sys
import types

import pandas as pd
import backtrader as bt


def _is_strategy_class(value) -> bool:
    return isinstance(value, type) and issubclass(value, bt.Strategy) and value is not bt.Strategy


def _load_custom_strategy_class(code: str, class_name: str | None) -> type[bt.Strategy]:
    """Compile and load a custom strategy from user-provided code."""
    if not code or not code.strip():
        raise ValueError("custom_strategy_code is required.")

    module_name = "__sandbox_custom_strategy__"
    module = types.ModuleType(module_name)
    module.__dict__["bt"] = bt
    module.__dict__["__builtins__"] = __builtins__
    sys.modules[module_name] = module
    namespace = module.__dict__

    exec(code, namespace, namespace)  # noqa: S102 — safe: we are inside a sandboxed container

    if class_name:
        candidate = namespace.get(class_name)
        if not _is_strategy_class(candidate):
            raise ValueError(
                f"Class '{class_name}' was not found or is not a backtrader Strategy subclass."
            )
        return candidate

    strategy_classes = [v for v in namespace.values() if _is_strategy_class(v)]
    if not strategy_classes:
        raise ValueError("No Strategy subclass found in custom_strategy_code.")
    if len(strategy_classes) > 1:
        raise ValueError("Multiple Strategy classes found. Set custom_strategy_class to choose one.")

    return strategy_classes[0]


def _wrap_strategy(strategy_cls: type[bt.Strategy]) -> type[bt.Strategy]:
    """Wrap the user strategy to capture trade logs."""

    class WrappedStrategy(strategy_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._trade_log = []

        def notify_order(self, order):
            parent = getattr(super(), "notify_order", None)
            if callable(parent):
                parent(order)

            if order.status in [order.Completed]:
                self._trade_log.append({
                    "datetime": str(bt.num2date(order.executed.dt)),
                    "type": "BUY" if order.isbuy() else "SELL",
                    "price": round(order.executed.price, 4),
                    "size": order.executed.size,
                    "value": round(order.executed.value, 2),
                    "commission": round(order.executed.comm, 4),
                })

    WrappedStrategy.__name__ = strategy_cls.__name__
    WrappedStrategy.__qualname__ = strategy_cls.__qualname__
    return WrappedStrategy


class PortfolioValueCapture(bt.Observer):
    """Captures portfolio value each bar."""
    lines = ('value',)
    plotinfo = dict(plot=False)

    def next(self):
        self.lines.value[0] = self._owner.broker.getvalue()


def run_backtest(job: dict) -> dict:
    """Execute a backtest from a job payload and return results."""
    # Load CSV data from the embedded string
    csv_data = job["csv_data"]
    df = pd.read_csv(io.StringIO(csv_data), index_col=0, parse_dates=True)

    fromdate = datetime.datetime.strptime(job.get("fromdate", "2000-01-01"), "%Y-%m-%d")
    todate = datetime.datetime.strptime(job.get("todate", "2099-12-31"), "%Y-%m-%d")

    # Load and wrap custom strategy
    strat_cls = _load_custom_strategy_class(
        code=job["custom_strategy_code"],
        class_name=job.get("custom_strategy_class"),
    )
    strat_cls = _wrap_strategy(strat_cls)

    # Build cerebro
    cerebro = bt.Cerebro(preload=True, runonce=True)
    cerebro.broker.set_cash(job.get("cash", 10000.0))
    cerebro.broker.setcommission(commission=job.get("commission", 0.001))

    data = bt.feeds.PandasData(dataname=df, fromdate=fromdate, todate=todate, openinterest=None)
    cerebro.adddata(data)

    strat_params = job.get("strategy_params") or {}
    cerebro.addstrategy(strat_cls, **strat_params)
    cerebro.addsizer(bt.sizers.FixedSize, stake=job.get("stake", 100))

    # Analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addobserver(PortfolioValueCapture)

    # Run
    results = cerebro.run()
    strat_result = results[0]

    final_value = cerebro.broker.getvalue()
    cash = job.get("cash", 10000.0)
    profit = final_value - cash
    profit_pct = (profit / cash) * 100.0

    # Trade log
    trades = getattr(strat_result, "_trade_log", [])

    # Portfolio values
    portfolio_values = []
    obs = getattr(strat_result.observers, "portfoliovaluecapture", None)
    if obs is not None:
        dt_line = strat_result.data.datetime
        val_line = obs.lines.value
        line_len = len(val_line)
        if line_len > 0:
            try:
                portfolio_values = [
                    {
                        "date": str(bt.num2date(dt_line[i]).date()),
                        "value": round(val_line[i], 2),
                    }
                    for i in range(-line_len + 1, 1)
                ]
            except (IndexError, ValueError, TypeError):
                pass

    # Analyzers
    analyzers = {}
    try:
        sharpe = strat_result.analyzers.sharpe.get_analysis()
        analyzers["sharpe_ratio"] = round(sharpe.get("sharperatio", 0) or 0, 4)
    except (AttributeError, KeyError, TypeError):
        analyzers["sharpe_ratio"] = None

    try:
        dd = strat_result.analyzers.drawdown.get_analysis()
        analyzers["max_drawdown_pct"] = round(dd.get("max", {}).get("drawdown", 0), 2)
        analyzers["max_drawdown_len"] = dd.get("max", {}).get("len", 0)
    except (AttributeError, KeyError, TypeError):
        analyzers["max_drawdown_pct"] = None

    try:
        ret = strat_result.analyzers.returns.get_analysis()
        analyzers["total_return_pct"] = round(ret.get("rtot", 0) * 100, 2)
    except (AttributeError, KeyError, TypeError):
        analyzers["total_return_pct"] = None

    try:
        sqn = strat_result.analyzers.sqn.get_analysis()
        analyzers["sqn"] = round(sqn.get("sqn", 0) or 0, 4)
        analyzers["sqn_trades"] = sqn.get("trades", 0)
    except (AttributeError, KeyError, TypeError):
        analyzers["sqn"] = None

    try:
        ta = strat_result.analyzers.trades.get_analysis()
        analyzers["trade_analysis"] = {
            "total_closed": ta.get("total", {}).get("closed", 0),
            "won": ta.get("won", {}).get("total", 0),
            "lost": ta.get("lost", {}).get("total", 0),
            "pnl_net_total": round(ta.get("pnl", {}).get("net", {}).get("total", 0), 2),
        }
    except (AttributeError, KeyError, TypeError):
        analyzers["trade_analysis"] = None

    return {
        "success": True,
        "strategy": "custom",
        "starting_cash": cash,
        "final_value": round(final_value, 2),
        "profit": round(profit, 2),
        "profit_pct": round(profit_pct, 2),
        "total_trades": len(trades),
        "trades": trades,
        "portfolio_values": portfolio_values,
        "analyzers": analyzers,
    }


def main():
    """Read job from stdin, run backtest, write result to stdout."""
    try:
        raw = sys.stdin.read()
        job = json.loads(raw)
        result = run_backtest(job)
        sys.stdout.write(json.dumps(result))
    except Exception as exc:
        error_result = {
            "success": False,
            "error": str(exc),
            "strategy": "custom",
            "starting_cash": 0,
            "final_value": 0,
            "profit": 0,
            "profit_pct": 0,
            "total_trades": 0,
            "trades": [],
            "portfolio_values": [],
            "analyzers": {},
        }
        sys.stdout.write(json.dumps(error_result))
        sys.exit(1)


if __name__ == "__main__":
    main()
