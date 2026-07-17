import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ActualMatch } from "../types";
import { Bracket } from "./Bracket";

const finishedMatch: ActualMatch = {
  match_id: 74,
  stage: "final",
  kickoff_at: "2026-06-30T04:30:00+08:00",
  home_team: "Germany",
  away_team: "Paraguay",
  result_kind: "actual",
  status: "finished",
  home_score: 1,
  away_score: 1,
  home_penalty_score: 3,
  away_penalty_score: 4,
  next_match_id: null,
  loser_next_match_id: null,
  home_source_match_id: null,
  home_source_outcome: null,
  away_source_match_id: null,
  away_source_outcome: null,
  source_url: "https://example.com/match/74",
  verified_at: "2026-06-30T07:00:00+08:00",
};

describe("Bracket team labels", () => {
  it("renders stable country codes in a dedicated column before full names", () => {
    const markup = renderToStaticMarkup(
      <Bracket actualMatches={[finishedMatch]} forecastMatches={[]} />,
    );

    expect(markup).toContain('class="team-code" aria-hidden="true">DE</span><strong title="Germany">Germany');
    expect(markup).toContain('class="team-code" aria-hidden="true">PY</span><strong title="Paraguay">Paraguay');
    expect(markup).not.toContain("🇩🇪");
  });
});
