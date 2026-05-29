"""
Bureau of Labor Statistics Collector
Free API v2 — register at https://data.bls.gov/registrationEngine/
Rate limit: 500 queries/day with key, 25 without

Series collected: Unemployment (U-3, U-6), Non-Farm Payrolls, PPI, ECI
"""
import json
import logging
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.aws_helpers import get_api_keys, write_to_raw_zone

logger = logging.getLogger(__name__)

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

SERIES_GROUPS = {
    "unemployment": ["LNS14000000", "LNS13327709"],  # U-3, U-6
    "payrolls":     ["CES0000000001"],                 # Total Nonfarm
    "ppi":          ["WPSFD4"],                        # PPI Finished Goods
    "eci":          ["CIU2010000000000A"],             # Employment Cost Index
}


def fetch_series_batch(series_ids: list[str], api_key: str) -> dict:
    """BLS v2 accepts up to 50 series per request — batch for efficiency."""
    from datetime import datetime
    current_year = datetime.now().year
    payload = {
        "seriesid":  series_ids,
        "startyear": str(current_year - 2),
        "endyear":   str(current_year),
        "registrationkey": api_key,
    }
    resp = requests.post(BLS_API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def lambda_handler(event: dict, context) -> dict:
    keys = get_api_keys()
    bls_key = keys.get("BLS_API_KEY", "")  # works without key, just lower limit

    results, errors = [], []

    for group_name, series_ids in SERIES_GROUPS.items():
        try:
            logger.info(f"Fetching BLS group: {group_name} {series_ids}")
            data = fetch_series_batch(series_ids, bls_key)

            if data.get("status") != "REQUEST_SUCCEEDED":
                raise ValueError(f"BLS API error: {data.get('message', 'Unknown')}")

            s3_path = write_to_raw_zone(data, source="bls", series_id=group_name)
            results.append({"group": group_name, "s3_path": s3_path, "status": "ok"})
        except Exception as e:
            logger.error(f"✗ {group_name}: {e}")
            errors.append({"group": group_name, "error": str(e)})

    return {"statusCode": 200 if not errors else 207, "collected": len(results), "errors": len(errors)}
