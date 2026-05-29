"""
Shared AWS helpers — used by all Lambda collectors.
Credentials come from the IAM execution role (never from env vars or hardcoded).
"""
import json
import os
import boto3
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_api_keys() -> dict[str, str]:
    """
    Fetch all API keys from Secrets Manager in one call.
    Cached so each Lambda invocation only calls SM once.
    """
    secret_arn = os.environ["SECRETS_ARN"]
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])


def get_s3_client():
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def write_to_raw_zone(data: Any, source: str, series_id: str) -> str:
    """
    Land raw data to S3 Bronze zone.
    Key pattern: raw/{source}/{year}/{month}/{day}/{series_id}.json
    Idempotent — same source+series+date always writes same key (safe to retry).
    """
    from datetime import datetime, timezone
    import json

    s3 = get_s3_client()
    bucket = os.environ["S3_BUCKET_RAW"]
    now = datetime.now(timezone.utc)

    key = f"raw/{source}/{now.year}/{now.month:02d}/{now.day:02d}/{series_id}.json"

    payload = {
        "source": source,
        "series_id": series_id,
        "ingested_at": now.isoformat(),
        "data": data,
    }

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, default=str),
        ContentType="application/json",
        # Server-side encryption (bucket policy enforces this too)
        ServerSideEncryption="AES256",
    )

    return f"s3://{bucket}/{key}"
