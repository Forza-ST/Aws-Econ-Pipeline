import { useEffect, useState } from "react";
import { api, type Summary, type CorrelationPair, type IndicatorPoint } from "./api/client";
import { CpiChart, ForecastChart } from "./components/Charts";
import { CorrelationHeatmap } from "./components/CorrelationHeatmap";

const FORECAST_KEYS = [
  { id: "cpi", label: "CPI" },
  { id: "unemployment", label: "Unemployment" },
  { id: "wti_oil", label: "WTI Oil" },
  { id: "gold", label: "Gold" },
];

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cpiData, setCpiData] = useState<IndicatorPoint[]>([]);
  const [correlations, setCorrelations] = useState<CorrelationPair[]>([]);
  const [forecastKey, setForecastKey] = useState("cpi");
  const [forecastPoints, setForecastPoints] = useState<
    Array<{ ds: string; yhat: number; yhat_lower: number; yhat_upper: number }>
  >([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [sum, ind, corr, fc] = await Promise.all([
          api.summary(),
          api.indicators("CPIAUCSL"),
          api.correlations(),
          api.forecast("cpi"),
        ]);
        if (cancelled) return;
        setSummary(sum);
        setCpiData(ind.observations);
        setCorrelations(corr.pairs);
        setForecastPoints(fc.points);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.forecast(forecastKey).then(
      (fc) => {
        if (!cancelled) setForecastPoints(fc.points);
      },
      (e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [forecastKey]);

  if (loading && !summary) {
    return (
      <div className="app">
        <p className="loading">Loading live pipeline data…</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Econ Pipeline Dashboard</h1>
          <p>Live data from S3 clean + curated zones · Jedi-Master account</p>
        </div>
        <span className="badge">REAL DATA · NO MOCKS</span>
      </header>

      {error && (
        <div className="error-banner">
          {error}
          {!import.meta.env.VITE_API_URL && (
            <div style={{ marginTop: "0.5rem" }}>
              Create <code>web/.env.local</code> with{" "}
              <code>VITE_API_URL=&lt;API Gateway URL&gt;</code>
            </div>
          )}
        </div>
      )}

      {summary && (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi-label">CPI YoY</div>
              <div className="kpi-value">{summary.cpi.yoy_pct}%</div>
              <div className="kpi-sub">
                Index {summary.cpi.cpi_index} · {summary.cpi.observation_date.slice(0, 10)}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Unemployment</div>
              <div className="kpi-value">{summary.unemployment_rate.value}%</div>
              <div className="kpi-sub">{summary.unemployment_rate.observation_date.slice(0, 10)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Fed Funds</div>
              <div className="kpi-value">{summary.fed_funds_rate.value}%</div>
              <div className="kpi-sub">{summary.fed_funds_rate.observation_date.slice(0, 10)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">ML Outputs</div>
              <div className="kpi-value">
                {summary.correlation_pairs} / {summary.forecasts_available}
              </div>
              <div className="kpi-sub">correlations · forecasts</div>
            </div>
          </div>

          <div className="panel" style={{ marginBottom: "1.25rem" }}>
            <h2>Commodity Watch</h2>
            <div className="commodity-grid">
              {summary.commodities.map((c) => (
                <div key={c.symbol} className="commodity-card">
                  <div className="label">{c.label}</div>
                  <div className="price">{c.close.toLocaleString()}</div>
                  <div className={`chg ${c.change_pct >= 0 ? "positive" : "negative"}`}>
                    {c.change_pct >= 0 ? "+" : ""}
                    {c.change_pct}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid-2">
            <div className="panel">
              <h2>CPI Trend (36 months)</h2>
              {cpiData.length > 0 ? <CpiChart data={cpiData} /> : <p className="loading">No CPI data</p>}
            </div>
            <div className="panel">
              <h2>Cross-Asset Correlations</h2>
              <CorrelationHeatmap pairs={correlations} />
            </div>
          </div>

          <div className="panel">
            <h2>Prophet Forecasts</h2>
            <div className="forecast-tabs">
              {FORECAST_KEYS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={forecastKey === f.id ? "active" : ""}
                  onClick={() => setForecastKey(f.id)}
                >
                  {f.label}
                </button>
              ))}
            </div>
            {forecastPoints.length > 0 ? (
              <ForecastChart points={forecastPoints} />
            ) : (
              <p className="loading">Loading forecast…</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
