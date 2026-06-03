import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from "recharts";
import type { IndicatorPoint } from "../api/client";

interface Props {
  data: IndicatorPoint[];
}

export function CpiChart({ data }: Props) {
  const chartData = [...data]
    .reverse()
    .map((d) => ({
      date: d.observation_date.slice(0, 7),
      index: d.value,
      yoy: d.yoy_pct != null ? Number(d.yoy_pct.toFixed(2)) : null,
    }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis yAxisId="left" tick={{ fontSize: 10 }} width={48} />
        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} width={40} unit="%" />
        <Tooltip
          contentStyle={{
            background: "#1c2430",
            border: "1px solid #2a3544",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Area
          yAxisId="left"
          type="monotone"
          dataKey="index"
          name="CPI Index"
          stroke="#3b82f6"
          fill="rgba(59, 130, 246, 0.15)"
          strokeWidth={2}
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="yoy"
          name="YoY %"
          stroke="#f59e0b"
          strokeWidth={2}
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

interface ForecastProps {
  points: Array<{ ds: string; yhat: number; yhat_lower: number; yhat_upper: number }>;
}

export function ForecastChart({ points }: ForecastProps) {
  const chartData = points.map((p) => ({
    date: p.ds.slice(0, 10),
    forecast: Number(p.yhat.toFixed(2)),
    lower: Number(p.yhat_lower.toFixed(2)),
    upper: Number(p.yhat_upper.toFixed(2)),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} width={52} />
        <Tooltip
          contentStyle={{
            background: "#1c2430",
            border: "1px solid #2a3544",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Line type="monotone" dataKey="upper" stroke="#64748b" strokeDasharray="4 4" dot={false} name="Upper" />
        <Line type="monotone" dataKey="forecast" stroke="#22c55e" strokeWidth={2} dot={false} name="Forecast" />
        <Line type="monotone" dataKey="lower" stroke="#64748b" strokeDasharray="4 4" dot={false} name="Lower" />
      </LineChart>
    </ResponsiveContainer>
  );
}
