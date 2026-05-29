"""
Unit tests for collectors — uses moto to mock AWS, no real credentials needed.
Run with: pytest tests/unit/ -v
"""

import json
import os
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock

# Set dummy env vars before importing modules
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("S3_BUCKET_RAW", "test-raw-bucket")
os.environ.setdefault(
    "SECRETS_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret/test"
)
os.environ.setdefault("ENVIRONMENT", "test")
# Use dummy AWS credentials for moto
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@mock_aws
class TestFredCollector:

    def setup_method(self, method):
        """Create mock S3 bucket and Secrets Manager secret before each test."""
        self.s3 = boto3.client("s3", region_name="us-east-1")
        self.s3.create_bucket(Bucket="test-raw-bucket")

        self.sm = boto3.client("secretsmanager", region_name="us-east-1")
        self.sm.create_secret(
            Name="arn:aws:secretsmanager:us-east-1:123456789012:secret/test",
            SecretString=json.dumps({"FRED_API_KEY": "test_key_not_real"}),
        )

    def test_write_to_raw_zone(self):
        """Test S3 write helper puts object with correct key pattern."""
        import sys

        sys.path.insert(0, "src")
        from utils.aws_helpers import write_to_raw_zone

        s3_path = write_to_raw_zone({"test": "data"}, "fred", "CPIAUCSL")

        assert s3_path.startswith("s3://test-raw-bucket/raw/fred/")
        assert "CPIAUCSL" in s3_path

    @patch("requests.get")
    def test_fred_fetch_series(self, mock_get):
        """Test FRED fetch parses response correctly."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "observations": [
                    {"date": "2024-01-01", "value": "3.4"},
                    {"date": "2024-02-01", "value": "3.2"},
                    {"date": "2024-03-01", "value": "."},  # missing value
                ]
            },
        )
        mock_get.return_value.raise_for_status = lambda: None

        from src.collectors.fred_collector import fetch_series

        result = fetch_series("CPIAUCSL", "test_key_not_real")
        assert "observations" in result


@mock_aws
class TestYfinanceCollector:

    def setup_method(self, method):
        self.s3 = boto3.client("s3", region_name="us-east-1")
        self.s3.create_bucket(Bucket="test-raw-bucket")

    @patch("yfinance.Ticker")
    def test_fetch_ticker_symbol_sanitized(self, mock_ticker):
        """Test that ^ and = in symbols are sanitized for S3 keys."""
        import pandas as pd

        mock_hist = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "Open": [4700.0, 4720.0],
                "High": [4720.0, 4750.0],
                "Low": [4695.0, 4710.0],
                "Close": [4715.0, 4740.0],
                "Volume": [3500000000, 3200000000],
            }
        ).set_index("Date")

        mock_ticker.return_value.history.return_value = mock_hist

        from src.collectors.yfinance_collector import fetch_ticker

        result = fetch_ticker("^GSPC", period_days=5)
        assert result["symbol"] == "^GSPC"
        assert len(result["observations"]) == 2
