"""
Time-Series Forecasting — CPI, GDP, Oil, Gold
Uses Prophet (Facebook) — lightweight, no GPU, runs in Lambda.

For interview: "We used Prophet for macro series due to its built-in
seasonality and holiday handling. For commodity series with stronger
cross-asset signals we'd use DeepAR on SageMaker."

Cost: Prophet runs in Lambda (128MB–512MB, free tier eligible).
"""
import logging
import os
from io import BytesIO
from datetime import datetime, timezone, timedelta

import boto3
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

FORECAST_SERIES = {
    "fred/CPIAUCSL":  {"horizon_months": 6,  "name": "CPI"},
    "fred/UNRATE":    {"horizon_months": 3,  "name": "Unemployment Rate"},
    "market/CLF":     {"horizon_months": 1,  "name": "WTI Oil"},
    "market/GCF":     {"horizon_months": 3,  "name": "Gold"},
}


def load_series_as_prophet_df(bucket: str, series_path: str) -> pd.DataFrame:
    """Prophet requires columns: ds (datetime), y (float)."""
    s3 = boto3.client("s3")
    prefix = f"clean/{series_path}"
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if not resp.get("Contents"):
        raise FileNotFoundError(f"No data: s3://{bucket}/{prefix}")

    latest_key = sorted(resp["Contents"], key=lambda x: x["LastModified"])[-1]["Key"]
    obj = s3.get_object(Bucket=bucket, Key=latest_key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    date_col = "observation_date" if "observation_date" in df.columns else "date"
    val_col  = "value"            if "value"            in df.columns else "close"

    prophet_df = pd.DataFrame({
        "ds": pd.to_datetime(df[date_col]),
        "y":  pd.to_numeric(df[val_col], errors="coerce"),
    }).dropna().sort_values("ds")

    return prophet_df


def run_prophet_forecast(df: pd.DataFrame, horizon_months: int, series_name: str) -> pd.DataFrame:
    """
    Fit Prophet and generate forecast.
    Returns DataFrame with columns: ds, yhat, yhat_lower, yhat_upper.
    """
    try:
        from prophet import Prophet
    except ImportError:
        logger.warning("Prophet not installed — returning mock forecast for demo")
        # Mock forecast for local dev without Prophet installed
        last_date = df["ds"].max()
        future_dates = pd.date_range(last_date, periods=horizon_months * 30, freq="D")
        last_val = df["y"].iloc[-1]
        noise = np.random.normal(0, last_val * 0.01, len(future_dates))
        return pd.DataFrame({
            "ds": future_dates,
            "yhat": last_val + np.cumsum(noise),
            "yhat_lower": last_val + np.cumsum(noise) - last_val * 0.02,
            "yhat_upper": last_val + np.cumsum(noise) + last_val * 0.02,
            "series": series_name,
            "is_forecast": True,
        })

    model = Prophet(
        changepoint_prior_scale=0.05,  # conservative — economic series are slow-moving
        seasonality_mode="multiplicative",
        yearly_seasonality=True,
        weekly_seasonality=False,  # macro data not weekly-seasonal
        daily_seasonality=False,
    )
    model.fit(df)

    periods = horizon_months * 30
    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)

    forecast["series"] = series_name
    forecast["is_forecast"] = forecast["ds"] > df["ds"].max()

    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "series", "is_forecast"]]


def lambda_handler(event: dict, context) -> dict:
    src_bucket  = os.environ.get("S3_BUCKET_CLEAN")
    dest_bucket = os.environ.get("S3_BUCKET_CURATED", src_bucket)

    results, errors = [], []
    s3 = boto3.client("s3")
    now = datetime.now(timezone.utc)

    for series_path, config in FORECAST_SERIES.items():
        try:
            logger.info(f"Forecasting: {config['name']}")
            df = load_series_as_prophet_df(src_bucket, series_path)
            forecast = run_prophet_forecast(df, config["horizon_months"], config["name"])

            buf = BytesIO()
            forecast.to_parquet(buf, compression="snappy", index=False)
            buf.seek(0)

            safe_name = config["name"].replace(" ", "_").lower()
            key = f"curated/forecasts/{now.year}/{now.month:02d}/{safe_name}_forecast.parquet"
            s3.put_object(Bucket=dest_bucket, Key=key, Body=buf.getvalue(), ServerSideEncryption="AES256")

            results.append({"series": config["name"], "key": key, "horizon_months": config["horizon_months"]})
            logger.info(f"  ✓ {config['name']} forecast → {key}")

        except Exception as e:
            logger.error(f"  ✗ {config['name']}: {e}")
            errors.append({"series": config["name"], "error": str(e)})

    return {"forecasts_generated": len(results), "errors": len(errors), "results": results}
