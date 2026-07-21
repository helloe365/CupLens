import { useMemo } from "react";

import type { PredictedMatch, Snapshot } from "../types";
import { isPredictedMatch, MatchCard } from "./MatchCard";

interface ForecastBreakdownProps {
  snapshot: Snapshot;
}

export function ForecastBreakdown({ snapshot }: ForecastBreakdownProps) {
  const nextMatch = useMemo(() => {
    return snapshot.forecast_matches
      .filter(
        (match): match is PredictedMatch =>
          match.result_kind === "forecast" && isPredictedMatch(match),
      )
      .slice()
      .sort((left, right) =>
        left.kickoff_at.localeCompare(right.kickoff_at),
      )[0];
  }, [snapshot]);

  return (
    <section
      className="panel forecast-breakdown"
      aria-labelledby="breakdown-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">NEXT FORECAST</p>
          <h2 id="breakdown-heading">下一场预测明细</h2>
        </div>
        <span className="data-note">
          {nextMatch ? `#${nextMatch.match_id}` : "暂无待赛预测"}
        </span>
      </div>

      {nextMatch ? (
        <MatchCard match={nextMatch} />
      ) : (
        <div className="state-card">当前快照没有可解析的预测比赛。</div>
      )}
    </section>
  );
}
