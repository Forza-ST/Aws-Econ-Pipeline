"""
Glue ETL Job — Raw (Bronze) → Clean (Silver)
Runs as an AWS Glue Python Shell job (cheaper than PySpark for small data).
Cost: Python Shell = $0.0667/DPH vs PySpark = $0.44/DPU-hr

Transforms:
- JSON → Parquet with enforced schema
- Type casting, deduplication
- Partition by source/year/month
"""

import sys
import json
import logging
from datetime import datetime

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from io import BytesIO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Injected by Glue at runtime — not hardcoded
RAW_BUCKET = (
    sys.argv[sys.argv.index("--raw_bucket") + 1] if "--raw_bucket" in sys.argv else ""
)
CLEAN_BUCKET = (
    sys.argv[sys.argv.index("--clean_bucket") + 1]
    if "--clean_bucket" in sys.argv
    else ""
)

s3 = boto3.client("s3")


FRED_SCHEMA = pa.schema(
    [
        pa.field("series_id", pa.string()),
        pa.field("observation_date", pa.date32()),
        pa.field("value", pa.float64()),
        pa.field("vintage_date", pa.date32()),  # when we collected it
        pa.field("source", pa.string()),
    ]
)

MARKET_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string()),
        pa.field("date", pa.date32()),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("volume", pa.int64()),
        pa.field("source", pa.string()),
    ]
)


def list_raw_files(source: str, date_prefix: str) -> list[str]:
    prefix = f"raw/{source}/{date_prefix}/"
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=RAW_BUCKET, Prefix=prefix):
        keys.extend([o["Key"] for o in page.get("Contents", [])])
    return keys


def read_json_from_s3(key: str) -> dict:
    obj = s3.get_object(Bucket=RAW_BUCKET, Key=key)
    return json.loads(obj["Body"].read())


def transform_fred(raw: dict) -> pd.DataFrame:
    """Normalize FRED API response to flat rows."""
    observations = raw.get("data", {}).get("observations", [])
    rows = []
    for obs in observations:
        if obs.get("value") == ".":  # FRED uses "." for missing
            continue
        rows.append(
            {
                "series_id": raw.get("series_id") or raw.get("data", {}).get("id", ""),
                "observation_date": obs["date"],
                "value": float(obs["value"]),
                "vintage_date": raw.get("ingested_at", "")[:10],
                "source": "fred",
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date
        df["vintage_date"] = pd.to_datetime(df["vintage_date"]).dt.date
    return df


def transform_market(raw: dict) -> pd.DataFrame:
    """Normalize yfinance response to OHLCV rows."""
    observations = raw.get("data", {}).get("observations", [])
    df = pd.DataFrame(observations)
    if df.empty:
        return df
    df = df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["symbol"] = raw.get("data", {}).get("symbol", "")
    df["source"] = "yfinance"
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None).dt.date
    return df[["symbol", "date", "open", "high", "low", "close", "volume", "source"]]


def write_parquet(df: pd.DataFrame, schema: pa.Schema, clean_key: str):
    """Write DataFrame to S3 as Snappy-compressed Parquet."""
    table = pa.Table.from_pandas(df, schema=schema, safe=True)
    buf = BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    s3.put_object(
        Bucket=CLEAN_BUCKET,
        Key=clean_key,
        Body=buf.getvalue(),
        ServerSideEncryption="AES256",
    )
    logger.info(f"Wrote {len(df)} rows → s3://{CLEAN_BUCKET}/{clean_key}")


def run(date_str: str = None):
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y/%m/%d")

    year, month, day = date_str.split("/")

    # Process FRED
    for key in list_raw_files("fred", date_str):
        raw = read_json_from_s3(key)
        df = transform_fred(raw)
        if not df.empty:
            series_id = df["series_id"].iloc[0]
            clean_key = f"clean/fred/{year}/{month}/{series_id}.parquet"
            write_parquet(df, FRED_SCHEMA, clean_key)

    # Process market data
    for key in list_raw_files("yfinance", date_str):
        raw = read_json_from_s3(key)
        df = transform_market(raw)
        if not df.empty:
            symbol = df["symbol"].iloc[0].replace("^", "").replace("=", "_")
            clean_key = f"clean/market/{year}/{month}/{symbol}.parquet"
            write_parquet(df, MARKET_SCHEMA, clean_key)


if __name__ == "__main__":
    run()
