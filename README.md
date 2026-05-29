# AWS Economic Analysis Pipeline

A production-grade data architecture project demonstrating ETL/ELT pipelines,
data lake design, ML-powered analysis, and CI/CD on AWS.

**Data Sources:** CPI · GDP · Unemployment · S&P 500 · NASDAQ · DJIA · WTI Oil · Brent · Gold · Silver · USD Index

## Architecture

```
Public APIs (FRED, BLS, yfinance, EIA)
    ↓  Lambda collectors (EventBridge scheduled)
S3 Raw Zone (Bronze) — immutable JSON
    ↓  AWS Glue Python Shell
S3 Clean Zone (Silver) — validated Parquet
    ↓  Glue ETL + dbt
S3 Curated Zone (Gold) — analytical datasets
    ↓  Lambda ML modules
Correlation Matrix · Prophet Forecasts
    ↓  Athena
Analyst queries · QuickSight dashboards
```

## Estimated Cost (Dev/Demo)
~$2.50/month — see `CURSOR_INSTRUCTIONS.md` for full breakdown.

## Setup
See [CURSOR_INSTRUCTIONS.md](./CURSOR_INSTRUCTIONS.md) for step-by-step implementation guide.

## Security
- OIDC-based GitHub Actions (no long-lived AWS keys)
- All secrets in AWS Secrets Manager
- S3 buckets: encrypted, versioned, public access blocked
- Gitleaks scanning on every commit and PR
- IAM least-privilege per Lambda function

## Key Technologies
Terraform · AWS Lambda · S3 · Glue · Athena · Secrets Manager · EventBridge ·
Apache Airflow (MWAA) · dbt · Great Expectations · Prophet · pandas · GitHub Actions
