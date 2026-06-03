import type { CorrelationPair } from "../api/client";

function corrColor(r: number | null): string {
  if (r == null || Number.isNaN(r)) return "rgba(100, 116, 139, 0.3)";
  const t = Math.max(-1, Math.min(1, r));
  if (t >= 0) {
    const g = Math.round(100 + t * 155);
    return `rgba(34, ${g}, 94, ${0.25 + t * 0.55})`;
  }
  const rVal = Math.round(100 + Math.abs(t) * 155);
  return `rgba(${rVal}, 68, 68, ${0.25 + Math.abs(t) * 0.55})`;
}

interface Props {
  pairs: CorrelationPair[];
}

export function CorrelationHeatmap({ pairs }: Props) {
  const valid = pairs.filter((p) => p.pearson_full != null || p.pearson_90d != null);
  if (valid.length === 0) {
    return <p className="loading">No correlation data</p>;
  }

  return (
    <div className="heatmap-wrap">
      <table className="heatmap">
        <thead>
          <tr>
            <th>Pair</th>
            <th>90d Pearson</th>
            <th>Full Pearson</th>
            <th>n</th>
          </tr>
        </thead>
        <tbody>
          {valid.map((p) => {
            const r90 = p.pearson_90d;
            const rFull = p.pearson_full;
            return (
              <tr key={p.pair_name}>
                <th style={{ textAlign: "left", fontWeight: 500 }}>{p.pair_name}</th>
                <td style={{ background: corrColor(r90) }}>
                  {r90 != null ? r90.toFixed(3) : "—"}
                </td>
                <td style={{ background: corrColor(rFull) }}>
                  {rFull != null ? rFull.toFixed(3) : "—"}
                </td>
                <td>{p.n_observations}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
