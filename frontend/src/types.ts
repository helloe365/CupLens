export type ResultKind = "actual" | "forecast";

export interface SourceRecord {
  source_id: string;
  role: "official" | "secondary";
  url: string;
  retrieved_at: string;
  verified_at: string;
  file_sha256: Record<string, string>;
}

export interface SnapshotProvenance {
  snapshot_id: string;
  generated_at: string;
  cutoff_at: string;
  model_version: string;
  data_sha256: string;
  random_seed: number;
  iterations: number;
  sources: SourceRecord[];
}

export interface SnapshotIndexEntry {
  snapshot_id: string;
  generated_at: string;
  cutoff_at: string;
  model_version: string;
  path: string;
}

export interface MatchBase {
  match_id: number;
  stage: string;
  kickoff_at: string;
  home_team: string;
  away_team: string;
  result_kind: ResultKind;
}

export interface ActualMatch extends MatchBase {
  result_kind: "actual";
  status: "finished";
  home_score: number;
  away_score: number;
  home_penalty_score: number | null;
  away_penalty_score: number | null;
  next_match_id: number | null;
  loser_next_match_id: number | null;
  home_source_match_id: number | null;
  home_source_outcome: "winner" | "loser" | null;
  away_source_match_id: number | null;
  away_source_outcome: "winner" | "loser" | null;
  source_url: string;
  verified_at: string;
}

export interface ScoreProbability {
  home_score: number;
  away_score: number;
  probability: number;
}

export interface PredictedMatch extends MatchBase {
  result_kind: "forecast";
  home_win: number;
  draw: number;
  away_win: number;
  home_advance: number;
  away_advance: number;
  home_xg: number;
  away_xg: number;
  top_scores: ScoreProbability[];
}

export interface ScheduledForecastMatch extends MatchBase {
  result_kind: "forecast";
  status: "scheduled";
  home_score: null;
  away_score: null;
  home_penalty_score: null;
  away_penalty_score: null;
  next_match_id: number | null;
  loser_next_match_id: number | null;
  home_source_match_id: number | null;
  home_source_outcome: "winner" | "loser" | null;
  away_source_match_id: number | null;
  away_source_outcome: "winner" | "loser" | null;
  source_url: string;
  verified_at: string;
}

export type ForecastMatch = PredictedMatch | ScheduledForecastMatch;

export interface TeamProbability {
  team: string;
  champion_probability: number;
  final_probability: number;
}

export interface BacktestResult {
  test_year: number;
  matches: number;
  accuracy: number;
  brier_score: number;
  log_loss: number;
  feature_cutoff_at: string;
  first_test_match_at: string;
}

export interface SnapshotMetrics {
  model_version?: string;
  feature_cutoff_rule?: string;
  results?: BacktestResult[];
  [key: string]: unknown;
}

export interface Snapshot extends SnapshotProvenance {
  actual_matches: ActualMatch[];
  forecast_matches: ForecastMatch[];
  team_probabilities: TeamProbability[];
  metrics: SnapshotMetrics;
  limitations: string[];
}

export interface CurrentForecastResponse extends SnapshotProvenance {
  team_probabilities: TeamProbability[];
  forecast_matches: ForecastMatch[];
}

export interface MatchPredictionResponse extends SnapshotProvenance {
  prediction: PredictedMatch;
}

export interface ProbabilityChange {
  team: string;
  change: number;
}

export interface SnapshotComparison {
  base_snapshot_id: string;
  target_snapshot_id: string;
  base: SnapshotProvenance;
  target: SnapshotProvenance;
  probability_changes: Record<string, number>;
  added_actual_match_ids: number[];
}

export interface ModelCardResponse extends SnapshotProvenance {
  metrics: SnapshotMetrics;
  limitations: string[];
  model_card: string;
}

export interface ToolCall {
  name:
    | "get_current_forecast"
    | "get_match_prediction"
    | "compare_snapshots"
    | "get_model_card";
  arguments: Record<string, unknown>;
}

export type AgentStructuredData =
  | CurrentForecastResponse
  | MatchPredictionResponse
  | SnapshotComparison
  | ModelCardResponse;

export interface ChatResponse {
  mode: "qwen" | "template";
  answer: string;
  tool_calls: ToolCall[];
  structured_data: AgentStructuredData;
  snapshot_id: string;
}
