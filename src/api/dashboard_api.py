"""
Dashboard API — serves real pipeline data via Athena (clean + curated Parquet on S3).
Routes:
  GET /summary
  GET /indicators/{series_id}
  GET /correlations
  GET /forecasts/{name}
  GET /commodities
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

COMMODITY_SYMBOLS = {
    "^GSPC": "S&P 500",
    "CL=F": "WTI Crude",
    "BZ=F": "Brent Crude",
    "GC=F": "Gold",
    "^VIX": "VIX",
    "DX-Y.NYB": "USD Index",
}

FORECAST_TABLES = {
    "cpi": "cpi_forecast",
    "unemployment": "unemployment_rate_forecast",
    "wti_oil": "wti_oil_forecast",
    "gold": "gold_forecast",
}


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def _athena() -> Any:
    return boto3.client("athena")


def run_query(sql: str) -> list[dict]:
    workgroup = os.environ["ATHENA_WORKGROUP"]
    database = os.environ["ATHENA_DATABASE"]
    output = os.environ["ATHENA_OUTPUT"]

    client = _athena()
    resp = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    qid = resp["QueryExecutionId"]

    for _ in range(60):
        status = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason", state)
            raise RuntimeError(f"Athena query failed: {reason}")
        time.sleep(0.5)
    else:
        raise TimeoutError("Athena query timed out")

    rows: list[dict] = []
    paginator = client.get_paginator("get_query_results")
    headers: list[str] = []
    for page in paginator.paginate(QueryExecutionId=qid):
        for i, row in enumerate(page["ResultSet"]["Rows"]):
            vals = [c.get("VarCharValue") for c in row["Data"]]
            if i == 0 and not headers:
                headers = vals
                continue
            rows.append(dict(zip(headers, vals)))
    return rows


def _num(row: dict, key: str, default: float = 0.0) -> float:
    v = row.get(key)
    if v is None or v == "":
        return default
    return float(v)


def handle_summary() -> dict:
    cpi_rows = run_query(
        """
        SELECT observation_date, value AS cpi_index,
               (value / LAG(value, 12) OVER (ORDER BY observation_date) - 1) * 100 AS yoy_pct
        FROM fred_indicators
        WHERE series_id = 'CPIAUCSL'
        ORDER BY observation_date DESC
        LIMIT 1
        """
    )
    unrate = run_query(
        """
        SELECT observation_date, value FROM fred_indicators
        WHERE series_id = 'UNRATE' ORDER BY observation_date DESC LIMIT 1
        """
    )
    fed = run_query(
        """
        SELECT observation_date, value FROM fred_indicators
        WHERE series_id = 'FEDFUNDS' ORDER BY observation_date DESC LIMIT 1
        """
    )
    corr_count = run_query("SELECT COUNT(*) AS n FROM correlation_matrix")
    fc_count = [{"n": "4"}]  # cpi, unemployment, wti_oil, gold forecast tables

    commodities = []
    for symbol, label in COMMODITY_SYMBOLS.items():
        rows = run_query(
            f"""
            WITH ranked AS (
              SELECT date, close,
                     LAG(close) OVER (ORDER BY date) AS prev_close
              FROM market_prices WHERE symbol = '{symbol}'
            )
            SELECT date, close,
                   CASE WHEN prev_close > 0 THEN (close - prev_close) / prev_close * 100 ELSE 0 END AS change_pct
            FROM ranked ORDER BY date DESC LIMIT 1
            """
        )
        if rows:
            r = rows[0]
            commodities.append(
                {
                    "symbol": symbol,
                    "label": label,
                    "date": r["date"],
                    "close": round(_num(r, "close"), 2),
                    "change_pct": round(_num(r, "change_pct"), 2),
                }
            )

    cpi = cpi_rows[0] if cpi_rows else {}
    u = unrate[0] if unrate else {}
    f = fed[0] if fed else {}

    return {
        "cpi": {
            "series_id": "CPIAUCSL",
            "observation_date": cpi.get("observation_date", ""),
            "cpi_index": round(_num(cpi, "cpi_index"), 2),
            "yoy_pct": round(_num(cpi, "yoy_pct"), 2),
        },
        "unemployment_rate": {
            "value": round(_num(u, "value"), 2),
            "observation_date": u.get("observation_date", ""),
        },
        "fed_funds_rate": {
            "value": round(_num(f, "value"), 2),
            "observation_date": f.get("observation_date", ""),
        },
        "correlation_pairs": int(_num(corr_count[0], "n") if corr_count else 0),
        "forecasts_available": int(_num(fc_count[0], "n") if fc_count else 4),
        "commodities": commodities,
    }


def handle_indicators(series_id: str) -> dict:
    sid = series_id.upper().replace("'", "")
    rows = run_query(
        f"""
        SELECT observation_date, value,
               (value / LAG(value, 12) OVER (ORDER BY observation_date) - 1) * 100 AS yoy_pct
        FROM fred_indicators
        WHERE series_id = '{sid}'
        ORDER BY observation_date DESC
        LIMIT 36
        """
    )
    for r in rows:
        r["value"] = round(_num(r, "value"), 4)
        if r.get("yoy_pct"):
            r["yoy_pct"] = round(_num(r, "yoy_pct"), 2)
    return {"series_id": sid, "observations": list(reversed(rows))}


def handle_correlations() -> dict:
    rows = run_query(
        """
        SELECT pair_name, series1, series2, pearson_90d, pearson_full, n_observations
        FROM correlation_matrix
        ORDER BY pair_name
        """
    )
    for r in rows:
        for k in ("pearson_90d", "pearson_full", "n_observations"):
            if r.get(k) not in (None, ""):
                r[k] = round(float(r[k]), 4) if k != "n_observations" else int(float(r[k]))
    return {"pairs": rows}


def handle_forecast(name: str) -> dict:
    table = FORECAST_TABLES.get(name.lower())
    if not table:
        raise ValueError(f"Unknown forecast: {name}. Valid: {list(FORECAST_TABLES)}")
    rows = run_query(
        f"""
        SELECT ds, yhat, yhat_lower, yhat_upper
        FROM {table}
        WHERE is_forecast = true
        ORDER BY ds
        LIMIT 120
        """
    )
    if not rows:
        rows = run_query(
            f"""
            SELECT ds, yhat, yhat_lower, yhat_upper
            FROM {table}
            ORDER BY ds DESC
            LIMIT 90
            """
        )
        rows = list(reversed(rows))
    for r in rows:
        r["yhat"] = round(_num(r, "yhat"), 2)
        r["yhat_lower"] = round(_num(r, "yhat_lower"), 2)
        r["yhat_upper"] = round(_num(r, "yhat_upper"), 2)
    return {"name": name, "points": rows}


def handle_commodities() -> dict:
    items = []
    for symbol, label in COMMODITY_SYMBOLS.items():
        latest = run_query(
            f"""
            SELECT date, close, volume FROM market_prices
            WHERE symbol = '{symbol}' ORDER BY date DESC LIMIT 1
            """
        )
        history = run_query(
            f"""
            SELECT date, close, volume FROM market_prices
            WHERE symbol = '{symbol}' ORDER BY date DESC LIMIT 60
            """
        )
        if not latest:
            continue
        l = latest[0]
        items.append(
            {
                "symbol": symbol,
                "label": label,
                "latest": {
                    "date": l["date"],
                    "close": round(_num(l, "close"), 2),
                    "volume": int(_num(l, "volume")),
                },
                "history": [
                    {
                        "date": h["date"],
                        "close": round(_num(h, "close"), 2),
                        "volume": int(_num(h, "volume")),
                    }
                    for h in reversed(history)
                ],
            }
        )
    return {"commodities": items}


def _route(event: dict) -> dict:
    path = (
        event.get("rawPath")
        or event.get("path")
        or event.get("requestContext", {}).get("http", {}).get("path")
        or "/"
    )
    path = path.rstrip("/") or "/"
    parts = [p for p in path.split("/") if p]

    if path.endswith("/summary") or path == "/summary":
        return handle_summary()
    if len(parts) >= 2 and parts[-2] == "indicators":
        return handle_indicators(parts[-1])
    if path.endswith("/correlations") or path == "/correlations":
        return handle_correlations()
    if len(parts) >= 2 and parts[-2] == "forecasts":
        return handle_forecast(parts[-1])
    if path.endswith("/commodities") or path == "/commodities":
        return handle_commodities()

    raise ValueError(f"Unknown route: {path}")


def lambda_handler(event: dict, context) -> dict:
    method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    try:
        return _response(200, _route(event))
    except ValueError as e:
        return _response(400, {"error": str(e)})
    except Exception as e:
        logger.exception("API error")
        return _response(500, {"error": str(e)})
