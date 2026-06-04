"""
Cross-Asset Correlation Engine
Computes rolling correlations between all economic series pairs:
  - Oil (WTI/Brent) ↔ CPI
  - Gold (GC=F) ↔ USD Index (DXY)
  - S&P 500 ↔ Unemployment
  - VIX ↔ Gold (safe-haven signal)

Cost: runs as Lambda (free tier) or Glue Python Shell ($0.067/DPH).
Uses pandas + scipy — no Spark needed at demo scale.
"""

import logging
import os
from io import BytesIO

import boto3
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

CROSS_ASSET_PAIRS = [
    ("fred/DCOILWTICO", "fred/CPIAUCSL", "Oil-CPI"),
    ("fred/DCOILWTICO", "fred/PCEPI", "Oil-PCE"),
    ("market/GC_F", "market/DX-Y.NYB", "Gold-USD"),
    ("market/GSPC", "fred/UNRATE", "SP500-Unemployment"),
    ("market/VIX", "market/GC_F", "VIX-Gold"),
    ("fred/T10Y2Y", "fred/FEDFUNDS", "Yield_Curve-Fed_Funds"),
    ("market/CL_F", "market/BZ_F", "WTI-Brent_Spread"),
]

WINDOWS = [(3, "30d"), (6, "90d"), (12, "365d")]  # months → legacy column suffixes


def load_series(bucket: str, series_path: str) -> pd.Series:
    """Load latest Parquet for a series and return as date-indexed Series."""
    s3 = boto3.client("s3")
    zone, series_id = series_path.split("/", 1)
    prefix = f"clean/{zone}/"

    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if not resp.get("Contents"):
        raise FileNotFoundError(f"No data found at s3://{bucket}/{prefix}")

    suffix = f"/{series_id}.parquet"
    matches = [o for o in resp["Contents"] if o["Key"].endswith(suffix)]
    if not matches:
        raise FileNotFoundError(
            f"No parquet matching *{suffix} under s3://{bucket}/{prefix}"
        )

    latest_key = sorted(matches, key=lambda x: x["LastModified"])[-1]["Key"]
    obj = s3.get_object(Bucket=bucket, Key=latest_key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    # Normalize to a date-indexed float series
    date_col = "observation_date" if "observation_date" in df.columns else "date"
    val_col = "value" if "value" in df.columns else "close"
    df[date_col] = pd.to_datetime(df[date_col])
    return df.set_index(date_col)[val_col].sort_index().dropna()


def compute_correlations(s1: pd.Series, s2: pd.Series, windows: list[int]) -> dict:
    """Compute Pearson and Spearman correlations over multiple rolling windows."""
    # Align on calendar month — FRED uses month-start, market uses month-end
    s1 = s1.copy()
    s2 = s2.copy()
    s1.index = pd.to_datetime(s1.index)
    s2.index = pd.to_datetime(s2.index)

    # Daily series → monthly mean before month-level join
    if len(s1) > len(s2) * 2:
        s1 = s1.resample("ME").mean()
    if len(s2) > len(s1) * 2:
        s2 = s2.resample("ME").mean()

    s1.index = s1.index.to_period("M")
    s2.index = s2.index.to_period("M")
    s1 = s1.groupby(level=0).last()
    s2 = s2.groupby(level=0).last()

    aligned = pd.concat([s1, s2], axis=1, join="inner")
    aligned.columns = ["s1", "s2"]
    aligned = aligned.dropna()

    if len(aligned) < 2:
        raise ValueError(
            f"Need at least 2 overlapping monthly observations, got {len(aligned)}"
        )

    results = {}
    for w_months, label in windows:
        if len(aligned) < w_months:
            results[f"pearson_{label}"] = None
            results[f"spearman_{label}"] = None
            continue

        recent = aligned.tail(w_months)
        pearson_r, pearson_p = stats.pearsonr(recent["s1"], recent["s2"])
        spearman_r, spearman_p = stats.spearmanr(recent["s1"], recent["s2"])

        results[f"pearson_{label}"] = round(pearson_r, 4)
        results[f"spearman_{label}"] = round(spearman_r, 4)
        results[f"pearson_p_{label}"] = round(pearson_p, 4)
        results[f"spearman_p_{label}"] = round(spearman_p, 4)

    # Full-period correlation
    pearson_full, _ = stats.pearsonr(aligned["s1"], aligned["s2"])
    results["pearson_full"] = round(pearson_full, 4)
    results["n_observations"] = len(aligned)

    return results


def lambda_handler(event: dict, context) -> dict:
    from datetime import datetime, timezone

    src_bucket = os.environ.get("S3_BUCKET_CLEAN")
    output_bucket = os.environ.get("S3_BUCKET_CURATED", src_bucket)
    if not src_bucket:
        raise ValueError("S3_BUCKET_CLEAN environment variable is required")

    matrix_rows = []
    errors = []

    for series1_path, series2_path, pair_name in CROSS_ASSET_PAIRS:
        try:
            logger.info(f"Computing correlations: {pair_name}")
            s1 = load_series(src_bucket, series1_path)
            s2 = load_series(src_bucket, series2_path)
            corr = compute_correlations(s1, s2, WINDOWS)
            matrix_rows.append(
                {
                    "pair_name": pair_name,
                    "series1": series1_path,
                    "series2": series2_path,
                    "computed_at": datetime.now(timezone.utc).isoformat(),
                    **corr,
                }
            )
            logger.info(f"  ✓ {pair_name}: 90d Pearson = {corr.get('pearson_90d')}")
        except Exception as e:
            logger.error(f"  ✗ {pair_name}: {e}")
            errors.append({"pair": pair_name, "error": str(e)})

    # Write correlation matrix to curated zone
    if matrix_rows:
        df = pd.DataFrame(matrix_rows)
        buf = BytesIO()
        df.to_parquet(buf, compression="snappy", index=False)
        buf.seek(0)

        s3 = boto3.client("s3")
        now = datetime.now(timezone.utc)
        key = f"curated/correlation_matrix/{now.year}/{now.month:02d}/correlation_matrix.parquet"
        s3.put_object(
            Bucket=output_bucket,
            Key=key,
            Body=buf.getvalue(),
            ServerSideEncryption="AES256",
        )
        logger.info(f"Correlation matrix written → s3://{output_bucket}/{key}")

    return {
        "pairs_computed": len(matrix_rows),
        "errors": len(errors),
        "error_details": errors,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import json

    print(json.dumps(lambda_handler({}, None), indent=2))
