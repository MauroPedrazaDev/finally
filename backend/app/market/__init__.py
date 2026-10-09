"""Market data subsystem for FinAlly.

Public API:
    PriceUpdate         - Immutable price snapshot dataclass
    PriceCache          - Thread-safe in-memory price store
    MarketDataSource    - Abstract interface for data providers
    MarketDataError / MarketDataRateLimitError / MarketDataAuthError - provider errors
    create_market_data_source - Factory that selects simulator or Massive
    start_market_data_source  - Create + start, falling back to the simulator on 401/403
    create_stream_router - FastAPI router factory for SSE endpoint
"""

from .cache import PriceCache
from .factory import create_market_data_source, start_market_data_source
from .interface import (
    MarketDataAuthError,
    MarketDataError,
    MarketDataRateLimitError,
    MarketDataSource,
)
from .models import PriceUpdate
from .stream import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "MarketDataError",
    "MarketDataRateLimitError",
    "MarketDataAuthError",
    "create_market_data_source",
    "start_market_data_source",
    "create_stream_router",
]
