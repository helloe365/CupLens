from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    field_serializer,
)

from app.schemas import Sha256, SourceRecord


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiResponseModel):
    status: Literal["ok"]
    snapshot_id: str | None


class SnapshotProvenance(ApiResponseModel):
    snapshot_id: str
    generated_at: AwareDatetime
    cutoff_at: AwareDatetime
    model_version: str
    data_sha256: Sha256
    random_seed: int
    iterations: PositiveInt
    sources: list[SourceRecord]


class SnapshotIndexEntry(ApiResponseModel):
    snapshot_id: str
    generated_at: AwareDatetime
    cutoff_at: AwareDatetime
    model_version: str
    path: str


class MatchBase(ApiResponseModel):
    match_id: int
    stage: str
    kickoff_at: AwareDatetime
    home_team: str
    away_team: str
    result_kind: Literal["actual", "forecast"]


class ActualMatch(MatchBase):
    result_kind: Literal["actual"]
    status: Literal["finished"]
    home_score: NonNegativeInt
    away_score: NonNegativeInt
    home_penalty_score: NonNegativeInt | None
    away_penalty_score: NonNegativeInt | None
    next_match_id: int | None
    loser_next_match_id: int | None
    home_source_match_id: int | None
    home_source_outcome: Literal["winner", "loser"] | None
    away_source_match_id: int | None
    away_source_outcome: Literal["winner", "loser"] | None
    source_url: str
    verified_at: AwareDatetime


class ScoreProbability(ApiResponseModel):
    home_score: NonNegativeInt
    away_score: NonNegativeInt
    probability: float = Field(ge=0.0, le=1.0)


class PredictedMatch(MatchBase):
    result_kind: Literal["forecast"]
    home_win: float = Field(ge=0.0, le=1.0)
    draw: float = Field(ge=0.0, le=1.0)
    away_win: float = Field(ge=0.0, le=1.0)
    home_advance: float = Field(ge=0.0, le=1.0)
    away_advance: float = Field(ge=0.0, le=1.0)
    home_xg: float = Field(ge=0.0)
    away_xg: float = Field(ge=0.0)
    top_scores: list[ScoreProbability]


class ScheduledForecastMatch(MatchBase):
    result_kind: Literal["forecast"]
    status: Literal["scheduled"]
    home_score: None
    away_score: None
    home_penalty_score: None
    away_penalty_score: None
    next_match_id: int | None
    loser_next_match_id: int | None
    home_source_match_id: int | None
    home_source_outcome: Literal["winner", "loser"] | None
    away_source_match_id: int | None
    away_source_outcome: Literal["winner", "loser"] | None
    source_url: str
    verified_at: AwareDatetime


ForecastMatch = PredictedMatch | ScheduledForecastMatch


class TeamProbability(ApiResponseModel):
    team: str
    champion_probability: float = Field(ge=0.0, le=1.0)
    final_probability: float = Field(ge=0.0, le=1.0)


class BacktestResult(ApiResponseModel):
    test_year: int
    matches: PositiveInt
    accuracy: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0)
    log_loss: float = Field(ge=0.0)
    feature_cutoff_at: AwareDatetime
    first_test_match_at: AwareDatetime

    @field_serializer("feature_cutoff_at", "first_test_match_at")
    def serialize_utc_offset(self, value: AwareDatetime) -> str:
        return value.isoformat()


class SnapshotMetrics(ApiResponseModel):
    model_config = ConfigDict(extra="allow")

    model_version: str | None = None
    feature_cutoff_rule: str | None = None
    results: list[BacktestResult] | None = None


class Snapshot(SnapshotProvenance):
    actual_matches: list[ActualMatch]
    forecast_matches: list[ForecastMatch]
    team_probabilities: list[TeamProbability]
    metrics: SnapshotMetrics
    limitations: list[str]


class CurrentForecastResponse(SnapshotProvenance):
    team_probabilities: list[TeamProbability]
    forecast_matches: list[ForecastMatch]


class MatchPredictionResponse(SnapshotProvenance):
    prediction: ForecastMatch


class SnapshotComparison(ApiResponseModel):
    base_snapshot_id: str
    target_snapshot_id: str
    base: SnapshotProvenance
    target: SnapshotProvenance
    probability_changes: dict[str, float]
    added_actual_match_ids: list[int]


class ModelCardResponse(SnapshotProvenance):
    metrics: SnapshotMetrics
    limitations: list[str]
    model_card: str


class ToolCall(ApiResponseModel):
    name: Literal[
        "get_current_forecast",
        "get_match_prediction",
        "compare_snapshots",
        "get_model_card",
    ]
    arguments: dict[str, Any]


AgentStructuredData = (
    CurrentForecastResponse
    | MatchPredictionResponse
    | SnapshotComparison
    | ModelCardResponse
)


class ChatResponse(ApiResponseModel):
    mode: Literal["qwen", "template"]
    answer: str
    tool_calls: list[ToolCall]
    structured_data: AgentStructuredData
    snapshot_id: str
