"""
FRED API Collector — CPI, GDP, Unemployment, PCE
Docs: https://fred.stlouisfed.org/docs/api/fred/

Free API key: https://fredaccount.stlouisfed.org/apikeys
Rate limit: 120 requests/60 seconds
"""
import logging
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.aws_helpers import get_api_keys, write_to_raw_zone

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Key macro series to collect
SERIES = {
    "CPIAUCSL":  "CPI All Urban Consumers (monthly)",
    "GDP":       "Gross Domestic Product (quarterly)",
    "UNRATE":    "Unemployment Rate (monthly)",
    "PCEPI":     "PCE Price Index (monthly)",
    "FEDFUNDS":  "Federal Funds Effective Rate (monthly)",
    "M2SL":      "M2 Money Stock (monthly)",
    "T10Y2Y":    "10Y-2Y Treasury Spread (daily)",
    "DCOILWTICO":"WTI Crude Oil Price (daily, from FRED)",
}


def fetch_series(series_id: str, api_key: str, observation_start: str = "2000-01-01") -> dict:
    """Fetch a single FRED series. Returns raw API response dict."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "sort_order": "desc",
        "limit": 100,  # last 100 obs per run — not full history (cost control)
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def lambda_handler(event: dict, context) -> dict:
    """
    Lambda entry point.
    Can be triggered by EventBridge (scheduled) or directly for testing.
    """
    keys = get_api_keys()
    fred_key = keys["FRED_API_KEY"]

    results = []
    errors = []

    for series_id, description in SERIES.items():
        try:
            logger.info(f"Fetching FRED series: {series_id}")
            data = fetch_series(series_id, fred_key)
            s3_path = write_to_raw_zone(data, source="fred", series_id=series_id)
            results.append({"series_id": series_id, "s3_path": s3_path, "status": "ok"})
            logger.info(f"✓ {series_id} → {s3_path}")
        except Exception as e:
            logger.error(f"✗ {series_id} failed: {e}")
            errors.append({"series_id": series_id, "error": str(e)})

    if errors:
        logger.warning(f"{len(errors)} series failed: {[e['series_id'] for e in errors]}")

    return {
        "statusCode": 200 if not errors else 207,
        "collected": len(results),
        "errors": len(errors),
        "results": results,
    }


# ── Local development runner ──────────────────────────────────────────────
if __name__ == "__main__":
    # For local testing: set env vars and run with python fred_collector.py
    # Requires: AWS_PROFILE or credentials, SECRETS_ARN, S3_BUCKET_RAW set
    import json
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))
