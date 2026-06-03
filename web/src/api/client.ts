const base = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "");

if (!base) {
  console.warn("VITE_API_URL not set — API calls will fail until .env.local is configured");
}

async function fetchJson<T>(path: string): Promise<T> {
  if (!base) throw new Error("Set VITE_API_URL in web/.env.local");
  const res = await fetch(`${base}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error((err as { error?: string }).error ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export interface Summary {
  cpi: { series_id: string; observation_date: string; cpi_index: number; yoy_pct: number };
  unemployment_rate: { value: number; observation_date: string };
  fed_funds_rate: { value: number; observation_date: string };
  correlation_pairs: number;
  forecasts_available: number;
  commodities: Array<{
    symbol: string;
    label: string;
    date: string;
    close: number;
    change_pct: number;
  }>;
  data_as_of: string;
}

export interface IndicatorPoint {
  observation_date: string;
  value: number;
  yoy_pct?: number;
}

export interface CorrelationPair {
  pair_name: string;
  series1: string;
  series2: string;
  pearson_90d: number | null;
  pearson_full: number | null;
  n_observations: number;
}

export interface ForecastPoint {
  ds: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
}

export const api = {
  summary: () => fetchJson<Summary>("/summary"),
  indicators: (seriesId: string) =>
    fetchJson<{ series_id: string; observations: IndicatorPoint[] }>(
      `/indicators/${seriesId}`,
    ),
  correlations: () =>
    fetchJson<{ pairs: CorrelationPair[] }>("/correlations"),
  forecast: (name: string) =>
    fetchJson<{ name: string; points: ForecastPoint[] }>(`/forecasts/${name}`),
  commodities: () =>
    fetchJson<{
      commodities: Array<{
        symbol: string;
        label: string;
        latest: { date: string; close: number; volume: number };
        history: Array<{ date: string; close: number; volume: number }>;
      }>;
    }>("/commodities"),
};
