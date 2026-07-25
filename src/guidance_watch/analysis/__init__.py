"""Pure historical metrics and heuristic reliability scoring."""

from guidance_watch.analysis.bias import observed_tendency, tendency_phrase
from guidance_watch.analysis.linker import link_claims_for_period, revision_direction
from guidance_watch.analysis.metrics import (
    absolute_error_pct,
    downward_revision_frequency,
    inside_range,
    latest_range_hit_rate,
    mean_absolute_error,
    median_signed_error,
    midpoint,
    original_range_hit_rate,
    revision_frequency,
    signed_error_pct,
)
from guidance_watch.analysis.scoring import calculate_assessment, map_total_to_label

__all__ = [
    "absolute_error_pct",
    "calculate_assessment",
    "downward_revision_frequency",
    "inside_range",
    "latest_range_hit_rate",
    "link_claims_for_period",
    "map_total_to_label",
    "mean_absolute_error",
    "median_signed_error",
    "midpoint",
    "observed_tendency",
    "original_range_hit_rate",
    "revision_direction",
    "revision_frequency",
    "signed_error_pct",
    "tendency_phrase",
]
