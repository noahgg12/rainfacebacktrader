"""
Rainface Backtrader API Server

FastAPI server that wraps the backtrader engine for Rainface.
Run with: python server.py
"""
import os
import sys
import csv
import json
import re
import types
import datetime
import traceback
from typing import Optional
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import backtrader as bt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from strategies import STRATEGY_REGISTRY

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Rainface Backtrader API",
    description="Backtesting engine for Rainface",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Rainface frontend can connect from any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base path for data files
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datas")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class BacktestRequest(BaseModel):
    strategy: str = Field(..., description="Strategy key, e.g. 'sma_cross' or 'rsi'")
    data_file: str = Field(
        default="orcl-1995-2014.txt",
        description="CSV filename inside the datas/ folder",
    )
    cash: float = Field(default=10000.0, description="Starting cash")
    commission: float = Field(default=0.001, description="Broker commission (0.001 = 0.1%)")
    stake: int = Field(default=100, description="Fixed position size")
    fromdate: Optional[str] = Field(default="2000-01-01", description="Start date YYYY-MM-DD")
    todate: Optional[str] = Field(default="2005-12-31", description="End date YYYY-MM-DD")
    strategy_params: Optional[dict] = Field(
        default=None,
        description="Strategy-specific params, e.g. {'fast_period': 10, 'slow_period': 30}",
    )
    custom_strategy_code: Optional[str] = Field(
        default=None,
        description="Custom Python strategy code. Used when strategy='custom'.",
    )
    custom_strategy_class: Optional[str] = Field(
        default=None,
        description="Optional class name inside custom_strategy_code to execute.",
    )


class TradeEntry(BaseModel):
    datetime: str
    type: str
    price: float
    size: float
    value: float
    commission: float


class PortfolioPoint(BaseModel):
    date: str
    value: float


class BacktestResponse(BaseModel):
    success: bool
    strategy: str
    starting_cash: float
    final_value: float
    profit: float
    profit_pct: float
    total_trades: int
    trades: list[TradeEntry]
    portfolio_values: list[PortfolioPoint]
    analyzers: dict


class DataImportRequest(BaseModel):
    provider: str = Field(
        default="auto",
        description="Data provider: 'auto' (Yahoo first, Massive fallback), 'yahoo', or 'massive'.",
    )
    symbols: list[str] = Field(..., description="List of symbols to import, e.g. ['AAPL', 'BTC-USD']")
    start: str = Field(..., description="Start date YYYY-MM-DD")
    end: str = Field(..., description="End date YYYY-MM-DD")
    timespan: str = Field(default="day", description="Only 'day' is supported")
    multiplier: int = Field(default=1, description="Only 1 is supported for now")
    adjusted: bool = Field(default=True, description="Request adjusted bars where provider supports it")
    api_key: Optional[str] = Field(default=None, description="Massive API key. Falls back to MASSIVE_API_KEY env var.")


class DataImportResult(BaseModel):
    symbol: str
    filename: Optional[str] = None
    bars: Optional[int] = None
    error: Optional[str] = None


class DataImportResponse(BaseModel):
    success: bool
    imported: list[DataImportResult]
    failed: list[DataImportResult]


# ---------------------------------------------------------------------------
# Custom observer to capture portfolio values over time
# ---------------------------------------------------------------------------
class PortfolioValueCapture(bt.Observer):
    """Silent observer that captures portfolio value each bar."""
    lines = ('value',)
    plotinfo = dict(plot=False)

    def next(self):
        self.lines.value[0] = self._owner.broker.getvalue()


# ---------------------------------------------------------------------------
# Data import helpers
# ---------------------------------------------------------------------------
def _sanitize_symbol_for_filename(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", symbol.upper())


def _to_massive_ticker(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith("-USD") and len(normalized) > 4:
        base = normalized[:-4]
        return f"X:{base}USD"
    return normalized


def _fetch_yahoo_daily_rows(symbol: str, start: str, end: str, adjusted: bool) -> list[tuple]:
    start_dt = datetime.datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    end_dt = datetime.datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    period1 = int(start_dt.timestamp())
    period2 = int((end_dt + datetime.timedelta(days=1)).timestamp())

    encoded_symbol = quote(symbol.strip().upper(), safe="^=.-_")
    include_adjusted = "true" if adjusted else "false"
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history&includeAdjustedClose={include_adjusted}"
    )

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 RainfaceBacktrader/1.0",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8").strip()
        except Exception:
            pass
        raise RuntimeError(f"Yahoo HTTP {exc.code}: {detail or exc.reason}")
    except URLError as exc:
        raise RuntimeError(f"Yahoo request failed: {exc.reason}")

    chart = payload.get("chart", {})
    if chart.get("error"):
        message = chart["error"].get("description") or chart["error"].get("code") or "unknown error"
        raise RuntimeError(f"Yahoo request failed: {message}")

    results = chart.get("result") or []
    if not results:
        return []

    result = results[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote_data = (indicators.get("quote") or [{}])[0]
    opens = quote_data.get("open") or []
    highs = quote_data.get("high") or []
    lows = quote_data.get("low") or []
    closes = quote_data.get("close") or []
    volumes = quote_data.get("volume") or []
    adj_data = (indicators.get("adjclose") or [{}])[0]
    adj_closes = adj_data.get("adjclose") or []

    by_date = {}
    for idx, timestamp in enumerate(timestamps):
        if idx >= len(opens) or idx >= len(highs) or idx >= len(lows) or idx >= len(closes):
            continue

        o = opens[idx]
        h = highs[idx]
        l = lows[idx]
        c = closes[idx]
        if o is None or h is None or l is None or c is None:
            continue

        volume = 0
        if idx < len(volumes) and volumes[idx] is not None:
            volume = int(float(volumes[idx]))

        adj_close = float(c)
        if adjusted and idx < len(adj_closes) and adj_closes[idx] is not None:
            adj_close = float(adj_closes[idx])

        date_str = datetime.datetime.fromtimestamp(int(timestamp), datetime.timezone.utc).date().isoformat()
        by_date[date_str] = (float(o), float(h), float(l), float(c), float(adj_close), volume)

    rows = []
    for date_str in sorted(by_date):
        o, h, l, c, adj_c, v = by_date[date_str]
        rows.append((date_str, o, h, l, c, adj_c, v))
    return rows


def _fetch_massive_daily_rows(ticker: str, start: str, end: str, api_key: str, adjusted: bool) -> list[tuple]:
    encoded_ticker = quote(ticker, safe=":")
    adjusted_value = "true" if adjusted else "false"
    next_url = (
        f"https://api.massive.com/v2/aggs/ticker/{encoded_ticker}/range/1/day/{start}/{end}"
        f"?adjusted={adjusted_value}&sort=asc&limit=50000&apiKey={api_key}"
    )
    results = []

    while next_url:
        request = Request(next_url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8").strip()
            except Exception:
                pass
            if exc.code == 401:
                raise RuntimeError("HTTP 401 Unauthorized. Verify Massive API key.")
            raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}")
        except URLError as exc:
            raise RuntimeError(f"Massive request failed: {exc.reason}")

        status = payload.get("status")
        if status not in ("OK", "DELAYED"):
            detail = payload.get("error") or payload.get("message") or f"status={status}"
            raise RuntimeError(f"Massive request failed: {detail}")

        results.extend(payload.get("results") or [])
        raw_next = payload.get("next_url")
        if raw_next:
            separator = "&" if "?" in raw_next else "?"
            next_url = f"{raw_next}{separator}apiKey={api_key}"
        else:
            next_url = ""

    by_date = {}
    for item in results:
        epoch_ms = item.get("t")
        if epoch_ms is None:
            continue
        value = datetime.datetime.fromtimestamp(epoch_ms / 1000.0, datetime.timezone.utc)
        date_str = value.date().isoformat()
        by_date[date_str] = (
            float(item.get("o", 0.0)),
            float(item.get("h", 0.0)),
            float(item.get("l", 0.0)),
            float(item.get("c", 0.0)),
            float(item.get("c", 0.0)),
            int(item.get("v", 0) or 0),
        )

    rows = []
    for date_str in sorted(by_date):
        o, h, l, c, adj_c, v = by_date[date_str]
        rows.append((date_str, o, h, l, c, adj_c, v))
    return rows


def _write_backtrader_csv(file_path: str, rows: list[tuple]) -> None:
    with open(file_path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"])
        for date_str, o, h, l, c, adj_c, v in rows:
            writer.writerow(
                [
                    date_str,
                    f"{o:.8f}",
                    f"{h:.8f}",
                    f"{l:.8f}",
                    f"{c:.8f}",
                    f"{adj_c:.8f}",
                    int(v),
                ]
            )


def _is_strategy_class(value) -> bool:
    return isinstance(value, type) and issubclass(value, bt.Strategy) and value is not bt.Strategy


def _load_custom_strategy_class(code: str, class_name: Optional[str]) -> type[bt.Strategy]:
    if not code or not code.strip():
        raise ValueError("custom_strategy_code is required when strategy='custom'.")

    module_name = "__rainface_custom_strategy__"
    module = types.ModuleType(module_name)
    module.__dict__["bt"] = bt
    module.__dict__["__builtins__"] = __builtins__
    # Backtrader class creation can read sys.modules[__name__].
    # Registering the dynamic module avoids KeyError during class definition.
    sys.modules[module_name] = module
    namespace = module.__dict__

    try:
        exec(code, namespace, namespace)
    except Exception as exc:
        raise ValueError(f"Custom strategy code failed to compile/execute: {exc}")

    if class_name:
        candidate = namespace.get(class_name)
        if not _is_strategy_class(candidate):
            raise ValueError(
                f"custom_strategy_class '{class_name}' was not found or is not a backtrader Strategy subclass."
            )
        return candidate

    strategy_classes = [value for value in namespace.values() if _is_strategy_class(value)]
    if not strategy_classes:
        raise ValueError("No strategy class found in custom_strategy_code. Define a class inheriting bt.Strategy.")
    if len(strategy_classes) > 1:
        raise ValueError("Multiple strategy classes found. Set custom_strategy_class to choose one.")

    return strategy_classes[0]


def _wrap_custom_strategy_with_trade_capture(strategy_cls: type[bt.Strategy]) -> type[bt.Strategy]:
    class RainfaceWrappedStrategy(strategy_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._rainface_trade_log = []

        def notify_order(self, order):
            parent_notify = getattr(super(), "notify_order", None)
            if callable(parent_notify):
                parent_notify(order)

            if order.status in [order.Completed]:
                self._rainface_trade_log.append(
                    {
                        "datetime": str(bt.num2date(order.executed.dt)),
                        "type": "BUY" if order.isbuy() else "SELL",
                        "price": round(order.executed.price, 4),
                        "size": order.executed.size,
                        "value": round(order.executed.value, 2),
                        "commission": round(order.executed.comm, 4),
                    }
                )

    RainfaceWrappedStrategy.__name__ = strategy_cls.__name__
    RainfaceWrappedStrategy.__qualname__ = strategy_cls.__qualname__
    return RainfaceWrappedStrategy


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "engine": "backtrader", "version": bt.__version__}


@app.get("/strategies")
def list_strategies():
    """List all available strategies and their configurable parameters."""
    result = []
    for key, info in STRATEGY_REGISTRY.items():
        result.append({
            "key": key,
            "name": info["name"],
            "description": info["description"],
            "params": info["params"],
        })
    return {"strategies": result}


@app.get("/data")
def list_data_files():
    """List available data files in the datas/ directory."""
    files = []
    for f in sorted(os.listdir(DATA_DIR)):
        if f.endswith((".txt", ".csv")):
            path = os.path.join(DATA_DIR, f)
            files.append({
                "filename": f,
                "size_bytes": os.path.getsize(path),
            })
    return {"data_files": files}


@app.post("/data/import", response_model=DataImportResponse)
def import_data_files(req: DataImportRequest):
    provider = req.provider.lower().strip()
    if provider not in {"auto", "yahoo", "massive"}:
        raise HTTPException(status_code=400, detail="provider must be one of: auto, yahoo, massive.")
    if req.timespan.lower() != "day":
        raise HTTPException(status_code=400, detail="Only timespan='day' is supported.")
    if req.multiplier != 1:
        raise HTTPException(status_code=400, detail="Only multiplier=1 is supported.")
    if not req.symbols:
        raise HTTPException(status_code=400, detail="At least one symbol is required.")

    try:
        start_dt = datetime.datetime.strptime(req.start, "%Y-%m-%d").date()
        end_dt = datetime.datetime.strptime(req.end, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start/end date. Use YYYY-MM-DD.")

    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start cannot be after end.")

    api_key = (req.api_key or os.environ.get("MASSIVE_API_KEY", "")).strip()
    if provider == "massive" and not api_key:
        raise HTTPException(status_code=400, detail="Massive API key missing. Provide api_key or set MASSIVE_API_KEY.")

    imported: list[DataImportResult] = []
    failed: list[DataImportResult] = []

    for symbol in req.symbols:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            continue

        try:
            rows = []
            source_provider = ""
            provider_errors = []

            if provider in {"auto", "yahoo"}:
                try:
                    rows = _fetch_yahoo_daily_rows(
                        symbol=clean_symbol,
                        start=req.start,
                        end=req.end,
                        adjusted=req.adjusted,
                    )
                    if rows:
                        source_provider = "yahoo"
                except Exception as exc:
                    provider_errors.append(f"yahoo: {exc}")

            if not rows and provider in {"auto", "massive"}:
                if not api_key:
                    provider_errors.append("massive: MASSIVE_API_KEY missing")
                else:
                    try:
                        rows = _fetch_massive_daily_rows(
                            ticker=_to_massive_ticker(clean_symbol),
                            start=req.start,
                            end=req.end,
                            api_key=api_key,
                            adjusted=req.adjusted,
                        )
                        if rows:
                            source_provider = "massive"
                    except Exception as exc:
                        provider_errors.append(f"massive: {exc}")

            if not rows:
                error_text = "; ".join(provider_errors) if provider_errors else "No bars returned from providers."
                failed.append(DataImportResult(symbol=clean_symbol, error=error_text))
                continue

            filename_symbol = _sanitize_symbol_for_filename(clean_symbol)
            filename = f"{filename_symbol}-1day-{req.start}-to-{req.end}-{source_provider}.txt"
            file_path = os.path.join(DATA_DIR, filename)
            _write_backtrader_csv(file_path, rows)

            imported.append(DataImportResult(symbol=clean_symbol, filename=filename, bars=len(rows)))

        except Exception as exc:
            failed.append(DataImportResult(symbol=clean_symbol, error=str(exc)))

    return DataImportResponse(
        success=len(failed) == 0,
        imported=imported,
        failed=failed,
    )


@app.post("/backtest/run", response_model=BacktestResponse)
def run_backtest(req: BacktestRequest):
    """Run a backtest and return results as JSON."""

    use_custom_strategy = req.strategy == "custom" or bool((req.custom_strategy_code or "").strip())

    # Validate strategy
    if not use_custom_strategy and req.strategy not in STRATEGY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{req.strategy}'. Available: {list(STRATEGY_REGISTRY.keys())}",
        )

    # Validate data file
    data_path = os.path.join(DATA_DIR, req.data_file)
    if not os.path.exists(data_path):
        raise HTTPException(
            status_code=400,
            detail=f"Data file '{req.data_file}' not found. Use GET /data to list available files.",
        )

    try:
        # Parse dates
        fromdate = datetime.datetime.strptime(req.fromdate, "%Y-%m-%d")
        todate = datetime.datetime.strptime(req.todate, "%Y-%m-%d")

        # --- Build Cerebro ---
        cerebro = bt.Cerebro()
        cerebro.broker.set_cash(req.cash)
        cerebro.broker.setcommission(commission=req.commission)

        # Load data
        data = bt.feeds.GenericCSVData(
            dataname=data_path,
            fromdate=fromdate,
            todate=todate,
            nullvalue=0.0,
            dtformat="%Y-%m-%d",
            datetime=0,
            open=1,
            high=2,
            low=3,
            close=4,
            volume=6,
            openinterest=-1,
        )
        cerebro.adddata(data)

        # Add strategy with params
        if use_custom_strategy:
            try:
                strat_cls = _load_custom_strategy_class(
                    code=req.custom_strategy_code or "",
                    class_name=req.custom_strategy_class,
                )
                strat_cls = _wrap_custom_strategy_with_trade_capture(strat_cls)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        else:
            strat_info = STRATEGY_REGISTRY[req.strategy]
            strat_cls = strat_info["cls"]

        strat_params = req.strategy_params or {}
        cerebro.addstrategy(strat_cls, **strat_params)

        # Sizer
        cerebro.addsizer(bt.sizers.FixedSize, stake=req.stake)

        # Analyzers
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")

        # Portfolio value observer
        cerebro.addobserver(PortfolioValueCapture)

        # --- Run ---
        results = cerebro.run()
        strat_result = results[0]

        # --- Extract results ---
        final_value = cerebro.broker.getvalue()
        profit = final_value - req.cash
        profit_pct = (profit / req.cash) * 100.0

        # Trades from strategy log
        if hasattr(strat_result, "trade_log") and strat_result.trade_log:
            trades = strat_result.trade_log
        elif hasattr(strat_result, "_rainface_trade_log"):
            trades = strat_result._rainface_trade_log
        else:
            trades = []

        # Portfolio values from observer
        portfolio_values = []
        obs = strat_result.observers.portfoliovaluecapture if hasattr(strat_result.observers, "portfoliovaluecapture") else None
        if obs is not None:
            dt_line = strat_result.data.datetime
            val_line = obs.lines.value
            for i in range(-len(val_line) + 1, 1):
                try:
                    d = bt.num2date(dt_line[i])
                    v = val_line[i]
                    portfolio_values.append({
                        "date": str(d.date()),
                        "value": round(v, 2),
                    })
                except Exception:
                    pass

        # Analyzers
        analyzers = {}
        try:
            sharpe = strat_result.analyzers.sharpe.get_analysis()
            analyzers["sharpe_ratio"] = round(sharpe.get("sharperatio", 0) or 0, 4)
        except Exception:
            analyzers["sharpe_ratio"] = None

        try:
            dd = strat_result.analyzers.drawdown.get_analysis()
            analyzers["max_drawdown_pct"] = round(dd.get("max", {}).get("drawdown", 0), 2)
            analyzers["max_drawdown_len"] = dd.get("max", {}).get("len", 0)
        except Exception:
            analyzers["max_drawdown_pct"] = None

        try:
            ret = strat_result.analyzers.returns.get_analysis()
            analyzers["total_return_pct"] = round(ret.get("rtot", 0) * 100, 2)
        except Exception:
            analyzers["total_return_pct"] = None

        try:
            sqn = strat_result.analyzers.sqn.get_analysis()
            analyzers["sqn"] = round(sqn.get("sqn", 0) or 0, 4)
            analyzers["sqn_trades"] = sqn.get("trades", 0)
        except Exception:
            analyzers["sqn"] = None

        try:
            ta = strat_result.analyzers.trades.get_analysis()
            analyzers["trade_analysis"] = {
                "total_closed": ta.get("total", {}).get("closed", 0),
                "won": ta.get("won", {}).get("total", 0),
                "lost": ta.get("lost", {}).get("total", 0),
                "pnl_net_total": round(ta.get("pnl", {}).get("net", {}).get("total", 0), 2),
            }
        except Exception:
            analyzers["trade_analysis"] = None

        return BacktestResponse(
            success=True,
            strategy=req.strategy,
            starting_cash=req.cash,
            final_value=round(final_value, 2),
            profit=round(profit, 2),
            profit_pct=round(profit_pct, 2),
            total_trades=len(trades),
            trades=trades,
            portfolio_values=portfolio_values,
            analyzers=analyzers,
        )

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("RAINFACE_BT_PORT", 8420))
    print(f"🚀 Rainface Backtrader API starting on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
