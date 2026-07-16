import type { ActualMatch, ForecastMatch } from "../types";
import { MatchCard } from "./MatchCard";

interface BracketProps {
  actualMatches: ActualMatch[];
  forecastMatches: ForecastMatch[];
}

const stages = [
  ["round_of_32", "32 强"],
  ["round_of_16", "16 强"],
  ["quarterfinal", "四分之一决赛"],
  ["semifinal", "半决赛"],
  ["third_place", "三四名赛"],
  ["final", "决赛"],
] as const;

export function Bracket({ actualMatches, forecastMatches }: BracketProps) {
  const allMatches = [...actualMatches, ...forecastMatches].sort(
    (left, right) => left.match_id - right.match_id,
  );

  if (allMatches.length === 0) {
    return <div className="state-card">当前快照没有淘汰赛数据。</div>;
  }

  return (
    <div className="bracket" aria-label="世界杯淘汰赛赛程树">
      {stages.map(([stage, label]) => {
        const matches = allMatches.filter((match) => match.stage === stage);
        if (matches.length === 0) return null;

        return (
          <section className="bracket-stage" key={stage}>
            <header>
              <span>{label}</span>
              <small>{matches.length} 场</small>
            </header>
            <div className="bracket-stage__matches">
              {matches.map((match) => (
                <MatchCard compact key={match.match_id} match={match} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
