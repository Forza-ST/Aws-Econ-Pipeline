# Econ Pipeline Dashboard (React)

Live dashboard for the AWS econ pipeline — reads real data via API Gateway + Lambda from S3 Parquet.

## Setup

1. Deploy the API (terraform apply) and note the `dashboard_api_url` output.
2. Copy `.env.example` to `.env.local`:

```bash
VITE_API_URL=https://xxxx.execute-api.us-east-1.amazonaws.com
```

3. Install and run:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173

## API Endpoints

| Path | Data source |
|------|-------------|
| `GET /summary` | KPIs + commodity snapshot |
| `GET /indicators/CPIAUCSL` | FRED CPI time series |
| `GET /correlations` | Curated correlation matrix |
| `GET /forecasts/cpi` | Prophet CPI forecast |
| `GET /commodities` | Market symbols with history |

## Build for production

```bash
npm run build
# Static files in dist/ — host on S3+CloudFront or any static host
```
