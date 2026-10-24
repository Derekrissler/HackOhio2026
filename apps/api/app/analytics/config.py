"""Versioned MVP policies; no database configuration belongs here."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    method_version: Literal["0.1"] = "0.1"
    attempt_policy: Literal["latest_valid"] = "latest_valid"
    weight_policy: Literal["normalize_per_question"] = "normalize_per_question"
    question_policy: Literal["parts_preferred_no_whole_overlap"] = "parts_preferred_no_whole_overlap"
    recurring_error_min_observations: int = Field(default=2, ge=2, strict=True)
    student_min_questions: int = Field(default=2, ge=1, strict=True)
    practice_min_attempts: int = Field(default=2, ge=1, strict=True)
    class_min_students: int = Field(default=5, ge=2, strict=True)
    observed_performance_threshold: float = Field(default=0.70, ge=0, le=1)
    suppress_small_cohorts: bool = True
    include_unreviewed_errors: bool = True
    clustering_min_observations: int = Field(default=6, ge=3, strict=True)
    clustering_eps: float = Field(default=0.25, gt=0, le=2)
    clustering_min_samples: int = Field(default=3, ge=2, strict=True)
    clustering_max_observations: int = Field(default=2000, ge=6, strict=True)
