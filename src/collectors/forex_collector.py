"""
Forex & USD Index Collector
Free tier: https://open.er-api.com/v6/latest/USD (no key needed for basic)
Paid: https://exchangeratesapi.io (key needed for history)
"""
import logging, os, sys
import requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.aws_helpers import get_api_keys, write_to_raw_zone

logger = logging.getLogger(__name__)

FX_PAIRS = ["EUR", "JPY", "GBP", "CAD", "CNY", "CHF", "AUD"]  # vs USD


def fetch_rates() -> dict:
    """Free endpoint — no key required, refreshes daily."""
    resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # Filter to just the pairs we care about
    data["rates"] = {k: v for k, v in data["rates"].items() if k in FX_PAIRS}
    return data


def lambda_handler(event: dict, context) -> dict:
    try:
        data = fetch_rates()
        s3_path = write_to_raw_zone(data, source="forex", series_id="usd_rates")
        return {"statusCode": 200, "s3_path": s3_path}
    except Exception as e:
        logger.error(f"Forex collection failed: {e}")
        return {"statusCode": 500, "error": str(e)}
