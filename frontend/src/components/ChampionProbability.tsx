import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { probabilityPercent } from "../api";
import type { TeamProbability } from "../types";
import { ProbabilityValue } from "./ProbabilityValue";

interface ChampionProbabilityProps {
  probabilities: TeamProbability[];
}

export function ChampionProbability({ probabilities }: ChampionProbabilityProps) {
  if (probabilities.length === 0) {
    return <div className="state-card">当前快照没有球队概率数据。</div>;
  }

  const ordered = [...probabilities].sort(
    (left, right) => right.champion_probability - left.champion_probability,
  );
  const hasInvalidValue = ordered.some(
    ({ champion_probability: value }) =>
      !Number.isFinite(value) || value < 0 || value > 1,
  );

  return (
    <section className="panel probability-panel" aria-labelledby="champion-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">PRECOMPUTED CHAMPION RACE</p>
          <h2 id="champion-heading">夺冠概率</h2>
        </div>
        <span className="data-note">API 原值 · 仅显示格式化</span>
      </div>

      {hasInvalidValue ? (
        <div className="state-card state-card--error" role="alert">
          概率数据非法，图表已停止渲染，请核对快照。
        </div>
      ) : (
        <div className="chart-wrap" aria-label="四队夺冠概率条形图">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={ordered} layout="vertical" margin={{ left: 8, right: 20 }}>
              <CartesianGrid stroke="#244650" horizontal={false} />
              <XAxis
                type="number"
                domain={[0, 1]}
                tickFormatter={(value: number) => `${value * 100}%`}
                stroke="#91a8ae"
              />
              <YAxis
                dataKey="team"
                type="category"
                width={74}
                stroke="#d9e4e3"
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "rgba(219, 176, 96, 0.08)" }}
                formatter={(value) => [
                  probabilityPercent(Number(value)),
                  "夺冠概率",
                ]}
                contentStyle={{
                  background: "#0a222b",
                  border: "1px solid #355761",
                  borderRadius: "0",
                }}
              />
              <Bar
                dataKey="champion_probability"
                fill="#f4c95d"
                radius={[0, 2, 2, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="probability-list">
        {ordered.map((item, index) => (
          <article className="probability-row" key={item.team}>
            <span className="rank">{String(index + 1).padStart(2, "0")}</span>
            <strong>{item.team}</strong>
            <span className="probability-secondary">
              进决赛 <ProbabilityValue value={item.final_probability} />
            </span>
            <ProbabilityValue
              className="probability-primary"
              value={item.champion_probability}
            />
          </article>
        ))}
      </div>
    </section>
  );
}
