# Aws-Econ-Pipeline

> **Production-grade AWS data architecture** — ingesting 6 public economic APIs,
> building a 3-zone S3 data lake, running ML forecasting and cross-asset correlation,
> and serving analysts via Athena + QuickSight. Estimated cost: **~$2.50/month** for demo.

---

## Interactive Architecture Diagram

**[▶ Open Full Interactive Diagram](https://forza-st.github.io/Aws-Econ-Pipeline/architecture-diagram.html)**

The diagram is a full interactive walkthrough of all 7 pipeline layers.
Click any node to see the tech stack, design rationale, and interview talking points.
Tabs: Architecture · Cost Breakdown · GitHub & CI/CD.

---

## Data Sources

| Category | Series | Source |
|----------|--------|--------|
| Inflation | CPI-U, PCE, PPI | FRED, BLS |
| Growth | Real GDP, Retail Sales | FRED, Census |
| Labor | Unemployment U-3/U-6, Non-Farm Payrolls, ECI | FRED, BLS |
| Equities | S&P 500, NASDAQ, DJIA, VIX | yfinance |
| Commodities | WTI Oil, Brent Crude, Gold, Silver | yfinance futures |
| Currency | USD Index (DXY), EUR/USD, JPY/USD, GBP | yfinance, open.er-api |
| Fixed Income | 10Y Treasury, Fed Funds Rate, 10Y-2Y Spread | FRED |

---

## Architecture — 7 Layers

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1 — Data Sources                                 │
│  FRED · BLS · yfinance · EIA · Census · open.er-api     │
└──────────────────────┬──────────────────────────────────┘
                       │ Lambda collectors · EventBridge CRON
┌──────────────────────▼──────────────────────────────────┐
│  Layer 2 — Ingestion & Orchestration                    │
│  AWS Lambda · EventBridge · Airflow MWAA · SQS DLQ      │
└──────────────────────┬──────────────────────────────────┘
                       │ Raw JSON → S3 partitioned by source/date
┌──────────────────────▼──────────────────────────────────┐
│  Layer 3 — Data Lake (S3 + Glue Catalog)                │
│  Bronze (raw) → Silver (clean Parquet) → Gold (curated) │
│  Lake Formation RBAC · SSE-S3 encryption · versioning   │
└──────────────────────┬──────────────────────────────────┘
                       │ Glue Python Shell · dbt models
┌──────────────────────▼──────────────────────────────────┐
│  Layer 4 — Transform, Quality & Modeling                │
│  Glue ETL · dbt star schema · Great Expectations · Athena│
└──────────────────────┬──────────────────────────────────┘
                       │ Feature engineering
┌──────────────────────▼──────────────────────────────────┐
│  Layer 5 — AI / ML                                      │
│  Prophet forecasting · Cross-asset correlation engine   │
│  Anomaly detection (RCF) · Bedrock RAG (FOMC minutes)   │
└──────────────────────┬──────────────────────────────────┘
                       │ Curated Parquet
┌──────────────────────▼──────────────────────────────────┐
│  Layer 6 — Query Layer                                  │
│  Athena (dev) · Redshift star schema (prod)             │
│  fact_economic_indicators · dim_series · dim_date       │
└──────────────────────┬──────────────────────────────────┘
                       │ Analysts · dashboards · APIs
┌──────────────────────▼──────────────────────────────────┐
│  Layer 7 — Serving, BI & Alerting                       │
│  QuickSight · Grafana · API Gateway · SNS + CloudWatch  │
└─────────────────────────────────────────────────────────┘
```

---

## Cost — Dev / Demo Environment

| Service | Monthly Cost |
|---------|-------------|
| AWS Lambda (5 collectors + 3 ML functions) | $0.00 — free tier |
| S3 Data Lake (3 zones, ~500MB Parquet) | $0.01 |
| Glue Python Shell ETL | $1.47 |
| Glue Crawler (on-demand) | $0.44 |
| Secrets Manager (1 secret) | $0.40 |
| Athena (ad-hoc queries, replaces Redshift in dev) | $0.00 |
| EventBridge, SQS, CloudWatch | $0.00 — free tier |
| GitHub Actions CI/CD (public repo) | $0.00 — unlimited |
| **Total** | **~$2.33/month** |

> Redshift ($180/mo) and MWAA ($360/mo) are excluded from dev — replaced by Athena and scheduled Lambda.

---

## Security

| Layer | Control |
|-------|---------|
| Local | `.gitignore` blocks `.env`, `backend.hcl`, `*.tfvars`, `*.tfstate`, `*.pem` |
| Local | Pre-commit hooks: Gitleaks secret scan + nbstripout (no notebook data) |
| CI | Gitleaks full history scan on every PR — blocks merge on any secret detection |
| CI | pip-audit CVE scan on all Python dependencies |
| CI | Branch protection: no direct push to main, all checks must pass |
| AWS | GitHub Actions uses OIDC — zero long-lived AWS keys stored anywhere |
| AWS | API keys in Secrets Manager — fetched at Lambda runtime, never in env vars |
| AWS | IAM least-privilege — Lambda can only write to `/raw/*` S3 prefix |
| AWS | S3 public access blocked on all buckets · SSE-S3 encryption enforced |
| AWS | Athena workgroup hard-limits query scan to 1GB (cost + safety guard) |

---

## Repository Structure

```
Aws-Econ-Pipeline/
├── .github/workflows/
│   ├── ci.yml                 # PR checks: secret scan, lint, test, tf validate
│   ├── deploy.yml             # main branch: OIDC auth → terraform apply
│   └── data-quality.yml       # scheduled: Great Expectations checkpoints
├── infrastructure/terraform/
│   ├── modules/               # s3, lambda, glue, redshift
│   └── environments/dev/      # cost-minimized dev config
├── src/
│   ├── collectors/            # fred, bls, yfinance, forex, commodities
│   ├── transforms/            # glue_silver_job.py
│   ├── quality/               # ge_checkpoints.py
│   ├── ml/                    # correlation_engine.py, forecasting.py
│   └── utils/                 # aws_helpers.py
├── configs/
│   ├── airflow_dags/          # econ_pipeline_dag.py
│   ├── dbt/                   # dimensional models
│   └── great_expectations/    # expectation suites
├── tests/unit/                # pytest + moto (AWS mocked)
├── scripts/
│   ├── bootstrap_aws.sh       # one-time: state bucket, OIDC role
│   └── setup_secrets.sh       # store API keys in Secrets Manager
├── docs/
│   └── architecture-diagram.html  # interactive pipeline diagram
├── SETUP.md                   # step-by-step implementation guide
└── README.md
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Forza-ST/Aws-Econ-Pipeline.git
cd Aws-Econ-Pipeline

# 2. Install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 3. Configure environment
cp .env.example .env             # fill in your AWS profile and API keys

# 4. Bootstrap AWS (one-time)
bash scripts/bootstrap_aws.sh dev

# 5. Store API keys securely
bash scripts/setup_secrets.sh dev

# 6. Deploy infrastructure
cd infrastructure/terraform/environments/dev
terraform init -backend-config=backend.hcl
terraform apply
```

See [SETUP.md](./SETUP.md) for the complete implementation guide.

---

## Key Technologies

`Terraform` `AWS Lambda` `S3` `Glue` `Athena` `Redshift` `Secrets Manager`
`EventBridge` `Airflow MWAA` `dbt` `Great Expectations` `Prophet` `pandas`
`scipy` `pyarrow` `Amazon Bedrock` `GitHub Actions` `Python 3.11`
