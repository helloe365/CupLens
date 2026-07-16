from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    HttpUrl,
    NonNegativeInt,
    StringConstraints,
    model_validator,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class GroupStanding(BaseModel):
    rank: int
    team: str


class GroupSummary(BaseModel):
    group: str
    standings: list[GroupStanding]


class SourceRecord(BaseModel):
    source_id: str
    role: Literal["official", "secondary"]
    url: HttpUrl
    retrieved_at: AwareDatetime
    verified_at: AwareDatetime
    file_sha256: dict[str, Sha256]


class MatchRecord(BaseModel):
    match_id: int
    stage: str
    kickoff_at: AwareDatetime
    home_team: str
    away_team: str
    home_score: NonNegativeInt | None = None
    away_score: NonNegativeInt | None = None
    home_penalty_score: NonNegativeInt | None = None
    away_penalty_score: NonNegativeInt | None = None
    status: Literal["finished", "scheduled"]
    result_kind: Literal["actual", "forecast"]
    next_match_id: int | None = None
    loser_next_match_id: int | None = None
    home_source_match_id: int | None = None
    home_source_outcome: Literal["winner", "loser"] | None = None
    away_source_match_id: int | None = None
    away_source_outcome: Literal["winner", "loser"] | None = None
    source_url: str
    verified_at: AwareDatetime

    @model_validator(mode="after")
    def validate_result_state(self) -> "MatchRecord":
        if self.status == "finished":
            if (
                self.result_kind != "actual"
                or self.home_score is None
                or self.away_score is None
            ):
                raise ValueError("finished matches require actual scores")
        else:
            if (
                self.result_kind != "forecast"
                or self.home_score is not None
                or self.away_score is not None
                or self.home_penalty_score is not None
                or self.away_penalty_score is not None
            ):
                raise ValueError("scheduled matches cannot contain actual scores")

        has_home_penalties = self.home_penalty_score is not None
        has_away_penalties = self.away_penalty_score is not None
        if has_home_penalties != has_away_penalties:
            raise ValueError("penalty shootouts require both penalty scores")
        if has_home_penalties:
            if self.status != "finished" or self.home_score != self.away_score:
                raise ValueError("penalty shootouts require a finished tied match")
            if self.home_penalty_score == self.away_penalty_score:
                raise ValueError("penalty shootout scores cannot be tied")

        if (self.home_source_match_id is None) != (self.home_source_outcome is None):
            raise ValueError("home source match and outcome must be provided together")
        if (self.away_source_match_id is None) != (self.away_source_outcome is None):
            raise ValueError("away source match and outcome must be provided together")
        return self


class TournamentData(BaseModel):
    groups: list[GroupSummary]
    matches: list[MatchRecord]
    team_names: dict[str, str]
    sources: list[SourceRecord]
