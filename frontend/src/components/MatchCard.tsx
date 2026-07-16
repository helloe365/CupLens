import type { ActualMatch, ForecastMatch, PredictedMatch } from "../types";
import { ProbabilityValue } from "./ProbabilityValue";

interface MatchCardProps {
  match: ActualMatch | ForecastMatch;
  compact?: boolean;
}

const stageNames: Record<string, string> = {
  round_of_32: "32 强",
  round_of_16: "16 强",
  quarterfinal: "四分之一决赛",
  semifinal: "半决赛",
  third_place: "三四名赛",
  final: "决赛",
};

export function isPredictedMatch(
  match: ActualMatch | ForecastMatch,
): match is PredictedMatch {
  return match.result_kind === "forecast" && "home_win" in match;
}

function kickoff(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Shanghai",
    hour12: false,
  }).format(new Date(value));
}

export function MatchCard({ match, compact = false }: MatchCardProps) {
  const isActual = match.result_kind === "actual";

  return (
    <article
      className={`match-card match-card--${match.result_kind}${compact ? " match-card--compact" : ""}`}
    >
      <header className="match-card__header">
        <span>#{match.match_id} · {stageNames[match.stage] ?? match.stage}</span>
        <span className={`kind-label kind-label--${match.result_kind}`}>
          {isActual ? "ACTUAL · 真实赛果" : "FORECAST · 模型预测"}
        </span>
      </header>
      <p className="kickoff">北京时间 {kickoff(match.kickoff_at)}</p>

      <div className="match-up">
        <strong>{match.home_team}</strong>
        {isActual ? (
          <span className="actual-score">
            {match.home_score} : {match.away_score}
          </span>
        ) : (
          <span className="versus">VS</span>
        )}
        <strong>{match.away_team}</strong>
      </div>

      {isPredictedMatch(match) ? (
        <>
          <div className="outcome-grid" aria-label="90 分钟赛果概率">
            <span>
              主胜 <ProbabilityValue value={match.home_win} />
            </span>
            <span>
              平局 <ProbabilityValue value={match.draw} />
            </span>
            <span>
              客胜 <ProbabilityValue value={match.away_win} />
            </span>
          </div>
          {!compact && (
            <>
              <div className="advance-grid">
                <span>
                  {match.home_team} 晋级 <ProbabilityValue value={match.home_advance} />
                </span>
                <span>
                  {match.away_team} 晋级 <ProbabilityValue value={match.away_advance} />
                </span>
              </div>
              <p className="xg-line">
                预期进球 {match.home_xg.toFixed(2)} — {match.away_xg.toFixed(2)}
              </p>
              <div className="score-chips" aria-label="最可能比分">
                {match.top_scores.map((score) => (
                  <span key={`${score.home_score}-${score.away_score}`}>
                    {score.home_score}:{score.away_score}{" "}
                    <ProbabilityValue value={score.probability} />
                  </span>
                ))}
              </div>
            </>
          )}
        </>
      ) : !isActual ? (
        <p className="pending-copy">对阵将在上游比赛结束后确定，当前不补全概率。</p>
      ) : null}
    </article>
  );
}
