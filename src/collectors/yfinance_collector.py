"""
Market Data Collector — S&P 500, NASDAQ, DJIA, Gold (GC=F), Oil (CL=F), Silver (SI=F)
Uses yfinance (free, no API key needed).

IMPORTANT: yfinance uses Yahoo Finance's unofficial API.
For production, replace with Bloomberg/Refinitiv. For demo, this is fine.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.aws_helpers import write_to_raw_zone

logger = logging.getLogger(__name__)

TICKERS = {
    "^GSPC":  "S&P 500 Index",
    "^IXIC":  "NASDAQ Composite",
    "^DJI":   "Dow Jones Industrial Average",
    "^VIX":   "CBOE Volatility Index",
    "GC=F":   "Gold Futures (front month)",
    "CL=F":   "WTI Crude Oil Futures",
    "SI=F":   "Silver Futures",
    "BZ=F":   "Brent Crude Oil Futures",
    "DX-Y.NYB": "US Dollar Index (DXY)",
    "^TNX":   "10-Year Treasury Yield",
}


def fetch_ticker(symbol: str, period_days: int = 5) -> dict:
    """
    Fetch recent OHLCV for a ticker.
    period_days=5 keeps each run cheap — full history loaded separately.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=period_days)

    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

    if hist.empty:
        raise ValueError(f"No data returned for {symbol}")

    return {
        "symbol": symbol,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "observations": hist.reset_index().to_dict(orient="records"),
    }


def lambda_handler(event: dict, context) -> dict:
    results, errors = [], []

    for symbol, description in TICKERS.items():
        try:
            logger.info(f"Fetching: {symbol} ({description})")
            data = fetch_ticker(symbol)
            # Sanitize symbol for S3 key (^ and = are invalid)
            safe_symbol = symbol.replace("^", "").replace("=", "_").replace(".", "_")
            s3_path = write_to_raw_zone(data, source="yfinance", series_id=safe_symbol)
            results.append({"symbol": symbol, "s3_path": s3_path, "status": "ok"})
        except Exception as e:
            logger.error(f"✗ {symbol}: {e}")
            errors.append({"symbol": symbol, "error": str(e)})

    return {
        "statusCode": 200 if not errors else 207,
        "collected": len(results),
        "errors": len(errors),
        "results": results,
    }
