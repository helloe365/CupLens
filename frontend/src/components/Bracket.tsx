import { useEffect, useRef } from "react";

import type { ActualMatch, ForecastMatch } from "../types";

interface BracketProps {
  actualMatches: ActualMatch[];
  forecastMatches: ForecastMatch[];
}

type TournamentMatch = ActualMatch | ForecastMatch;
type BranchStage = "round_of_32" | "round_of_16" | "quarterfinal" | "semifinal";

interface BranchLevels {
  round_of_32: TournamentMatch[];
  round_of_16: TournamentMatch[];
  quarterfinal: TournamentMatch[];
  semifinal: TournamentMatch[];
}

const stageLabels: Record<BranchStage, string> = {
  round_of_32: "32 强",
  round_of_16: "16 强",
  quarterfinal: "四分之一决赛",
  semifinal: "半决赛",
};

const teamCodes: Record<string, string> = {
  "South Africa": "ZA",
  Canada: "CA",
  Germany: "DE",
  Paraguay: "PY",
  Netherlands: "NL",
  Morocco: "MA",
  Brazil: "BR",
  Japan: "JP",
  France: "FR",
  Sweden: "SE",
  "Côte d'Ivoire": "CI",
  Norway: "NO",
  Mexico: "MX",
  Ecuador: "EC",
  England: "EN",
  "Congo DR": "CD",
  USA: "US",
  "Bosnia and Herzegovina": "BA",
  Belgium: "BE",
  Senegal: "SN",
  Portugal: "PT",
  Croatia: "HR",
  Spain: "ES",
  Austria: "AT",
  Switzerland: "CH",
  Algeria: "DZ",
  Argentina: "AR",
  "Cabo Verde": "CV",
  Colombia: "CO",
  Ghana: "GH",
  Australia: "AU",
  Egypt: "EG",
};

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

function percent(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);
}

function winner(match: TournamentMatch): "home" | "away" | null {
  if (match.result_kind === "forecast") {
    if (!("home_advance" in match)) return null;
    return match.home_advance >= match.away_advance ? "home" : "away";
  }
  if (match.home_score !== match.away_score) {
    return match.home_score > match.away_score ? "home" : "away";
  }
  if (match.home_penalty_score !== null && match.away_penalty_score !== null) {
    return match.home_penalty_score > match.away_penalty_score ? "home" : "away";
  }
  return null;
}

function winningTeam(match: TournamentMatch): string | null {
  const side = winner(match);
  return side === "home" ? match.home_team : side === "away" ? match.away_team : null;
}

function BracketMatch({ match, featured = false }: { match: TournamentMatch; featured?: boolean }) {
  const winningSide = winner(match);
  const isPrediction = match.result_kind === "forecast";
  const homeValue = isPrediction && "home_advance" in match
    ? percent(match.home_advance)
    : match.result_kind === "actual"
      ? String(match.home_score)
      : "—";
  const awayValue = isPrediction && "away_advance" in match
    ? percent(match.away_advance)
    : match.result_kind === "actual"
      ? String(match.away_score)
      : "—";
  const topScore = isPrediction && "top_scores" in match ? match.top_scores[0] : null;
  const penalties = match.result_kind === "actual"
    && match.home_penalty_score !== null
    && match.away_penalty_score !== null
      ? `点球 ${match.home_penalty_score}:${match.away_penalty_score}`
      : null;

  return (
    <article
      aria-label={`${match.home_team} 对 ${match.away_team}`}
      className={`bracket-match bracket-match--${match.result_kind}${featured ? " bracket-match--featured" : ""}`}
    >
      <header>
        <span>#{match.match_id} · {kickoff(match.kickoff_at)}</span>
        <i aria-hidden="true" />
      </header>
      <div className={`bracket-team${winningSide === "home" ? " bracket-team--winner" : ""}`}>
        <span className="team-code" aria-hidden="true">{teamCodes[match.home_team] ?? "--"}</span>
        <strong title={match.home_team}>{match.home_team}</strong>
        <b>{homeValue}</b>
      </div>
      <div className={`bracket-team${winningSide === "away" ? " bracket-team--winner" : ""}`}>
        <span className="team-code" aria-hidden="true">{teamCodes[match.away_team] ?? "--"}</span>
        <strong title={match.away_team}>{match.away_team}</strong>
        <b>{awayValue}</b>
      </div>
      {(penalties || topScore) && (
        <div className="bracket-match__note">
          {penalties ?? `最可能比分 ${topScore?.home_score}:${topScore?.away_score}`}
        </div>
      )}
    </article>
  );
}

function StageColumn({
  matches,
  side,
  stage,
}: {
  matches: TournamentMatch[];
  side: "left" | "right";
  stage: BranchStage;
}) {
  const pairs: TournamentMatch[][] = [];
  for (let index = 0; index < matches.length; index += 2) {
    pairs.push(matches.slice(index, index + 2));
  }

  return (
    <section className={`tree-stage tree-stage--${side} tree-stage--${stage}`}>
      <header>
        <span>{stageLabels[stage]}</span>
        <small>{matches.length} 场</small>
      </header>
      <div className="tree-stage__pairs">
        {pairs.map((pair, pairIndex) => (
          <div
            className={`tree-pair${pair.length === 1 ? " tree-pair--single" : ""}`}
            key={`${stage}-${pairIndex}`}
          >
            {pair.map((match) => <BracketMatch key={match.match_id} match={match} />)}
          </div>
        ))}
      </div>
    </section>
  );
}

function buildBranches(allMatches: TournamentMatch[]): {
  left: BranchLevels;
  right: BranchLevels;
  finalMatch: TournamentMatch | null;
  thirdPlaceMatch: TournamentMatch | null;
} {
  const byId = new Map<number, TournamentMatch>();
  allMatches.forEach((match) => byId.set(match.match_id, match));

  const winnerIncoming = new Map<number, number[]>();
  for (const match of byId.values()) {
    if ("next_match_id" in match && match.next_match_id !== null) {
      const incoming = winnerIncoming.get(match.next_match_id) ?? [];
      incoming.push(match.match_id);
      winnerIncoming.set(match.next_match_id, incoming);
    }
  }

  function orderedParents(match: TournamentMatch): TournamentMatch[] {
    const explicit = "home_source_match_id" in match
      ? [match.home_source_match_id, match.away_source_match_id]
      : [];
    const ids = [...explicit, ...(winnerIncoming.get(match.match_id) ?? [])]
      .filter((id): id is number => id !== null);
    return [...new Set(ids)]
      .map((id) => byId.get(id))
      .filter((candidate): candidate is TournamentMatch => candidate !== undefined);
  }

  function levels(root: TournamentMatch): BranchLevels {
    const quarterfinal = orderedParents(root);
    const roundOf16 = quarterfinal.flatMap(orderedParents);
    const roundOf32 = roundOf16.flatMap(orderedParents);
    return {
      round_of_32: roundOf32,
      round_of_16: roundOf16,
      quarterfinal,
      semifinal: [root],
    };
  }

  const finalMatch = allMatches.find((match) => match.stage === "final") ?? null;
  const thirdPlaceMatch = allMatches.find((match) => match.stage === "third_place") ?? null;
  const semifinalIds = finalMatch ? winnerIncoming.get(finalMatch.match_id) ?? [] : [];
  let semifinals = semifinalIds
    .map((id) => byId.get(id))
    .filter((match): match is TournamentMatch => match !== undefined);

  if (semifinals.length < 2) {
    semifinals = allMatches
      .filter((match) => match.stage === "semifinal")
      .sort((left, right) => left.match_id - right.match_id);
  }

  if (finalMatch && semifinals.length >= 2) {
    semifinals = [...semifinals].sort((left, right) => (
      Number(winningTeam(right) === finalMatch.home_team)
      - Number(winningTeam(left) === finalMatch.home_team)
    ));
  }

  const empty: BranchLevels = {
    round_of_32: [],
    round_of_16: [],
    quarterfinal: [],
    semifinal: [],
  };

  return {
    left: semifinals[0] ? levels(semifinals[0]) : empty,
    right: semifinals[1] ? levels(semifinals[1]) : empty,
    finalMatch,
    thirdPlaceMatch,
  };
}

export function Bracket({ actualMatches, forecastMatches }: BracketProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const allMatches = [...actualMatches, ...forecastMatches]
    .filter((match, index, matches) => (
      matches.findIndex((candidate) => candidate.match_id === match.match_id) === index
    ));

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || window.matchMedia("(min-width: 1180px)").matches) return;
    container.scrollLeft = (container.scrollWidth - container.clientWidth) / 2;
  }, [allMatches.length]);

  if (allMatches.length === 0) {
    return <div className="state-card">当前快照没有淘汰赛数据。</div>;
  }

  const { left, right, finalMatch, thirdPlaceMatch } = buildBranches(allMatches);

  return (
    <div className="bracket-shell">
      <div
        aria-label="可横向滚动的世界杯完整淘汰赛对阵图"
        className="bracket-scroll"
        ref={scrollRef}
        role="region"
        tabIndex={0}
      >
        <div className="bracket-board">
          <StageColumn matches={left.round_of_32} side="left" stage="round_of_32" />
          <StageColumn matches={left.round_of_16} side="left" stage="round_of_16" />
          <StageColumn matches={left.quarterfinal} side="left" stage="quarterfinal" />
          <StageColumn matches={left.semifinal} side="left" stage="semifinal" />

          <section className="bracket-finals" aria-label="决赛与三四名赛">
            <header>
              <span>FINAL</span>
              <strong>2026</strong>
              <small>两条晋级路径在此汇合</small>
            </header>
            {finalMatch ? <BracketMatch featured match={finalMatch} /> : <div className="bracket-slot">决赛对阵待定</div>}
            <div className="third-place-label">三四名赛</div>
            {thirdPlaceMatch ? <BracketMatch match={thirdPlaceMatch} /> : <div className="bracket-slot">三四名赛待定</div>}
          </section>

          <StageColumn matches={right.semifinal} side="right" stage="semifinal" />
          <StageColumn matches={right.quarterfinal} side="right" stage="quarterfinal" />
          <StageColumn matches={right.round_of_16} side="right" stage="round_of_16" />
          <StageColumn matches={right.round_of_32} side="right" stage="round_of_32" />
        </div>
      </div>
      <p className="bracket-scroll-hint">在较小屏幕上可横向拖动，查看两侧完整赛区</p>
    </div>
  );
}
