"""Job search agent pipeline — ingest, evaluate, tailor, apply."""

from src.job_pipeline.orchestrator import (
    evaluate_job,
    inbound_job_event,
    mark_applied,
    process_job,
    process_job_record,
    tailor_job,
    transition_to_ready_to_apply,
    validate_and_route,
)
from src.job_pipeline.parser import parse_raw, compute_dedup_key, normalize_field
from src.job_pipeline.brief import get_jobs_for_brief
from src.job_pipeline.store import (
    count_job_funnel_stages,
    count_job_records,
    create_job_record,
    get_job_record,
    list_job_records,
    get_job_events,
    job_record_to_dict,
    job_event_to_dict,
)

__all__ = [
    "inbound_job_event",
    "process_job_record",
    "process_job",
    "evaluate_job",
    "tailor_job",
    "validate_and_route",
    "transition_to_ready_to_apply",
    "mark_applied",
    "get_jobs_for_brief",
    "parse_raw",
    "compute_dedup_key",
    "normalize_field",
    "create_job_record",
    "get_job_record",
    "count_job_records",
    "count_job_funnel_stages",
    "list_job_records",
    "get_job_events",
    "job_record_to_dict",
    "job_event_to_dict",
]
