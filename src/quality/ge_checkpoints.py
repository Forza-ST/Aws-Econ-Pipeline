"""
Great Expectations Data Quality Checkpoints
Validates Silver zone Parquet files on a schedule.

Cost: runs as Lambda or local script — no persistent compute needed.
"""
import logging
import os
import boto3
import pandas as pd
import pyarrow.parquet as pq
from io import BytesIO
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class Expectation:
    name: str
    check: Callable[[pd.DataFrame], bool]
    message: str


@dataclass
class CheckpointResult:
    series: str
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def success(self): return len(self.failed) == 0


# ── Expectation suites ────────────────────────────────────────────────────

FRED_EXPECTATIONS = [
    Expectation("no_nulls",         lambda df: df["value"].notna().all(),              "Values must not be null"),
    Expectation("cpi_range",        lambda df: df[df.series_id=="CPIAUCSL"]["value"].between(0, 500).all() if "CPIAUCSL" in df.series_id.values else True, "CPI must be 0–500"),
    Expectation("unrate_range",     lambda df: df[df.series_id=="UNRATE"]["value"].between(1, 30).all()   if "UNRATE"   in df.series_id.values else True, "Unemployment must be 1–30%"),
    Expectation("date_not_future",  lambda df: pd.to_datetime(df["observation_date"]).max() <= pd.Timestamp.today(), "No future dates"),
    Expectation("no_duplicates",    lambda df: not df.duplicated(["series_id", "observation_date"]).any(), "No duplicate series+date rows"),
]

MARKET_EXPECTATIONS = [
    Expectation("prices_positive",  lambda df: (df[["open","high","low","close"]] > 0).all().all(), "All prices must be positive"),
    Expectation("high_gte_low",     lambda df: (df["high"] >= df["low"]).all(),                     "High must be >= Low"),
    Expectation("volume_positive",  lambda df: (df["volume"] >= 0).all(),                           "Volume must be non-negative"),
    Expectation("no_nulls",         lambda df: df[["open","high","low","close"]].notna().all().all(),"No null OHLC values"),
]

OIL_GOLD_EXPECTATIONS = [
    Expectation("oil_range",   lambda df: df[df.symbol.isin(["CLF","BZF"])]["close"].between(10, 300).all() if not df[df.symbol.isin(["CLF","BZF"])].empty else True, "Oil price $10–$300"),
    Expectation("gold_range",  lambda df: df[df.symbol=="GCF"]["close"].between(500, 5000).all()            if not df[df.symbol=="GCF"].empty              else True, "Gold price $500–$5000"),
]


def read_parquet_from_s3(bucket: str, key: str) -> pd.DataFrame:
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


def run_checkpoint(df: pd.DataFrame, expectations: list[Expectation], series_name: str) -> CheckpointResult:
    result = CheckpointResult(series=series_name)
    for exp in expectations:
        try:
            if exp.check(df):
                result.passed.append(exp.name)
                logger.info(f"  ✓ {exp.name}")
            else:
                result.failed.append(f"{exp.name}: {exp.message}")
                logger.warning(f"  ✗ {exp.name}: {exp.message}")
        except Exception as e:
            result.failed.append(f"{exp.name}: exception — {e}")
    return result


def lambda_handler(event: dict, context) -> dict:
    bucket = os.environ["S3_BUCKET_CLEAN"]
    results = []

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    # Check FRED silver files
    for page in paginator.paginate(Bucket=bucket, Prefix="clean/fred/"):
        for obj in page.get("Contents", []):
            df = read_parquet_from_s3(bucket, obj["Key"])
            r = run_checkpoint(df, FRED_EXPECTATIONS, obj["Key"])
            results.append({"key": obj["Key"], "passed": r.passed, "failed": r.failed, "success": r.success})

    # Check market silver files
    for page in paginator.paginate(Bucket=bucket, Prefix="clean/market/"):
        for obj in page.get("Contents", []):
            df = read_parquet_from_s3(bucket, obj["Key"])
            expectations = MARKET_EXPECTATIONS + OIL_GOLD_EXPECTATIONS
            r = run_checkpoint(df, expectations, obj["Key"])
            results.append({"key": obj["Key"], "passed": r.passed, "failed": r.failed, "success": r.success})

    failures = [r for r in results if not r["success"]]
    if failures:
        logger.error(f"{len(failures)} checkpoints FAILED")
        # In prod: send SNS alert here

    return {"total": len(results), "passed": len(results) - len(failures), "failed": len(failures), "details": results}
