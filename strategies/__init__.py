"""
Rainface Backtrader Strategies Registry

All strategies are registered here so the server can discover them.
"""

from .sma_cross import SmaCrossStrategy
from .rsi import RsiStrategy
from .macd import MacdStrategy
from .bollinger import BollingerStrategy
from .ema_cross import EmaCrossStrategy
from .stochastic import StochasticStrategy

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
    "macd": {
        "cls": MacdStrategy,
        "name": "MACD Crossover",
        "description": "Buys when MACD line crosses above signal line, sells when it crosses below.",
        "params": {
            "fast_period": {"default": 12, "type": "int", "description": "Fast EMA period for MACD"},
            "slow_period": {"default": 26, "type": "int", "description": "Slow EMA period for MACD"},
            "signal_period": {"default": 9, "type": "int", "description": "Signal line EMA period"},
        }
    },
    "bollinger": {
        "cls": BollingerStrategy,
        "name": "Bollinger Bands Mean Reversion",
        "description": "Buys when price drops below lower Bollinger Band, sells when price rises above upper band.",
        "params": {
            "period": {"default": 20, "type": "int", "description": "Bollinger Bands lookback period"},
            "devfactor": {"default": 2.0, "type": "float", "description": "Standard deviation multiplier"},
        }
    },
    "ema_cross": {
        "cls": EmaCrossStrategy,
        "name": "EMA Crossover",
        "description": "Buys when fast EMA crosses above slow EMA, sells when it crosses below. More responsive than SMA.",
        "params": {
            "fast_period": {"default": 12, "type": "int", "description": "Fast EMA period"},
            "slow_period": {"default": 26, "type": "int", "description": "Slow EMA period"},
        }
    },
    "stochastic": {
        "cls": StochasticStrategy,
        "name": "Stochastic Oscillator",
        "description": "Buys when %K crosses above %D in oversold zone, sells when %K crosses below %D in overbought zone.",
        "params": {
            "k_period": {"default": 14, "type": "int", "description": "Stochastic %K period"},
            "d_period": {"default": 3, "type": "int", "description": "Stochastic %D smoothing period"},
            "oversold": {"default": 20, "type": "int", "description": "Oversold threshold (buy zone)"},
            "overbought": {"default": 80, "type": "int", "description": "Overbought threshold (sell zone)"},
        }
    },
}
