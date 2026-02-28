"""
Rainface Backtrader Strategies Registry

All strategies are registered here so the server can discover them.
"""

from .sma_cross import SmaCrossStrategy
from .rsi import RsiStrategy

# Registry: name -> (class, description, default_params)
STRATEGY_REGISTRY = {
    "sma_cross": {
        "cls": SmaCrossStrategy,
        "name": "SMA Crossover",
        "description": "Buys when fast SMA crosses above slow SMA, sells when it crosses below.",
        "params": {
            "fast_period": {"default": 10, "type": "int", "description": "Fast SMA period"},
            "slow_period": {"default": 30, "type": "int", "description": "Slow SMA period"},
        }
    },
    "rsi": {
        "cls": RsiStrategy,
        "name": "RSI Mean Reversion",
        "description": "Buys when RSI drops below oversold level, sells when RSI rises above overbought level.",
        "params": {
            "rsi_period": {"default": 14, "type": "int", "description": "RSI lookback period"},
            "oversold": {"default": 30, "type": "int", "description": "RSI oversold threshold (buy)"},
            "overbought": {"default": 70, "type": "int", "description": "RSI overbought threshold (sell)"},
        }
    },
}
