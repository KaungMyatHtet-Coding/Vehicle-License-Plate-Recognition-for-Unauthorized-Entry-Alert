"""Offline structural validation for the retained PostgreSQL migrations."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import get_args

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.schemas.decision import DecisionReason, DecisionStatus  # noqa: E402

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "202607310001_day9_data_model.sql"
)
PRODUCTION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260802000000_initial_schema.sql"
)
OUTCOME_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "202608020001_day11_detection_outcomes.sql"
)
HISTORICAL_MIGRATIONS = (MIGRATION, PRODUCTION_MIGRATION, OUTCOME_MIGRATION)

REQUIRED_PATTERNS = {
    "transaction": r"\Abegin;.*commit;\s*\Z",
    "authorized vehicles": r"create table public\.authorized_vehicles",
    "detection logs": r"create table public\.detection_logs",
    "settings": r"create table public\.app_settings",
    "normalized uniqueness": (
        r"constraint authorized_vehicles_normalized_plate_unique\s+"
        r"unique \(normalized_plate\)"
    ),
    "timestamps": r"created_at timestamptz not null default now\(\)",
    "updated-at trigger": r"create trigger authorized_vehicles_set_updated_at",
    "confidence bound": r"confidence between 0\.0 and 1\.0",
    "OCR states": r"ocr_status in \('recognized', 'manual_review'\)",
    "evidence pair": r"constraint detection_logs_evidence_pair",
    "evidence bucket format": (
        r"evidence_bucket ~ '\^\[a-z0-9\]\[a-z0-9\._-\]\{0,99\}\$'"
    ),
    "relative evidence path": (
        r"evidence_object_path !~ '\(\^/\|\\\\\|\(\^\|/\)"
        r"\\\.\\\.\(/\|\$\)\|\^\[A-Za-z\]:\)'"
    ),
    "finite non-negative timings function": (
        r"create or replace function public\.is_nonnegative_finite_timings"
    ),
    "finite non-negative timings constraint": (
        r"check \(public\.is_nonnegative_finite_timings\(timings\)\)"
    ),
    "indexes": r"create index detection_logs_created_at_idx",
    "RLS": r"alter table public\.authorized_vehicles enable row level security",
    "client revocation": (
        r"revoke all on table public\.authorized_vehicles from anon, authenticated"
    ),
}

FORBIDDEN_PATTERNS = {
    "embedded credential": r"(?i)(service_role_key|password|api_key)\s*=\s*['\"][^'\"]+",
    "client policy": r"(?i)create policy",
}

OUTCOME_PATTERNS = {
    "transaction": r"\Abegin;.*commit;\s*\Z",
    "decision column": r"add column decision text",
    "decision reason column": r"add column decision_reason text",
    "matched vehicle column": r"add column matched_vehicle_id uuid",
    "backfill": r"update public\.detection_logs",
    "decision constraint": r"constraint detection_logs_decision_reason",
    "authorized vehicle association": (r"constraint detection_logs_authorized_vehicle"),
    "vehicle foreign key": r"references public\.authorized_vehicles \(id\)",
    "restricted vehicle deletion": (
        r"references public\.authorized_vehicles \(id\)\s+on delete restrict"
    ),
    "authorized matched vehicle": (
        r"check \(decision <> 'AUTHORIZED' or matched_vehicle_id is not null\)"
    ),
    "decision index": r"create index detection_logs_decision_created_at_idx",
}

EXPECTED_STATUSES = set(get_args(DecisionStatus))
EXPECTED_REASONS = set(get_args(DecisionReason))
EXPECTED_REASON_MAP = {
    "AUTHORIZED": {"ACTIVE_MATCH"},
    "UNAUTHORIZED": {
        "VEHICLE_NOT_FOUND",
        "VEHICLE_INACTIVE",
        "VEHICLE_BLOCKED",
        "VEHICLE_NOT_YET_VALID",
        "VEHICLE_EXPIRED",
    },
    "MANUAL_REVIEW": {
        "OCR_EMPTY",
        "OCR_LOW_CONFIDENCE",
        "OCR_RESULT_INVALID",
        "DECISION_TIME_INVALID",
        "VEHICLE_RECORD_INVALID",
        "VEHICLE_LOOKUP_FAILED",
    },
}


def validate_schema(sql: str) -> list[str]:
    """Return deterministic validation failures without database or network access."""

    normalized = re.sub(r"--[^\n]*", "", sql).strip()
    patterns = (
        OUTCOME_PATTERNS
        if "add column decision text" in normalized.lower()
        else REQUIRED_PATTERNS
    )
    failures = [
        f"missing {name}"
        for name, pattern in patterns.items()
        if re.search(pattern, normalized, flags=re.DOTALL | re.IGNORECASE) is None
    ]
    failures.extend(
        f"forbidden {name}"
        for name, pattern in FORBIDDEN_PATTERNS.items()
        if re.search(pattern, normalized) is not None
    )
    if patterns is OUTCOME_PATTERNS:
        failures.extend(_validate_outcome_semantics(normalized))
    if normalized.count("(") != normalized.count(")"):
        failures.append("unbalanced parentheses")
    if "$$" in normalized and normalized.count("$$") % 2:
        failures.append("unbalanced dollar quoting")
    return failures


def _validate_outcome_semantics(sql: str) -> list[str]:
    """Validate exact Day 10 vocabulary, mapping, and safe migration ordering."""

    failures: list[str] = []
    lowered = sql.lower()
    update_at = lowered.find("update public.detection_logs")
    not_null_at = lowered.find("alter column decision set not null")
    constraint_at = lowered.find("constraint detection_logs_decision_reason")
    if min(update_at, not_null_at, constraint_at) < 0 or not (
        update_at < not_null_at <= constraint_at
    ):
        failures.append("invalid backfill ordering")

    backfill_pattern = (
        r"update public\.detection_logs\s+set\s+"
        r"decision = 'MANUAL_REVIEW',\s+decision_reason = case\s+"
        r"when review_reason = 'OCR_EMPTY' then 'OCR_EMPTY'\s+"
        r"when review_reason = 'OCR_LOW_CONFIDENCE' then 'OCR_LOW_CONFIDENCE'\s+"
        r"else 'OCR_RESULT_INVALID'\s+end;"
    )
    if re.search(backfill_pattern, sql, flags=re.DOTALL | re.IGNORECASE) is None:
        failures.append("invalid decision backfill")

    constraint_end = lowered.find(
        "constraint detection_logs_authorized_vehicle", constraint_at
    )
    constraint_sql = (
        sql[constraint_at:constraint_end]
        if constraint_at >= 0 and constraint_end > constraint_at
        else ""
    )
    tokens = set(re.findall(r"'([A-Z_]+)'", constraint_sql))
    if tokens != EXPECTED_STATUSES | EXPECTED_REASONS:
        failures.append("invalid Day 10 decision vocabulary")

    actual_mapping: dict[str, set[str]] = {}
    authorized = re.search(
        r"decision = 'AUTHORIZED'\s+and decision_reason = '([^']+)'",
        constraint_sql,
        flags=re.DOTALL,
    )
    actual_mapping["AUTHORIZED"] = {authorized.group(1)} if authorized else set()
    for status in ("UNAUTHORIZED", "MANUAL_REVIEW"):
        match = re.search(
            rf"decision = '{status}'\s+and decision_reason in \((.*?)\)",
            constraint_sql,
            flags=re.DOTALL,
        )
        actual_mapping[status] = (
            set(re.findall(r"'([A-Z_]+)'", match.group(1))) if match else set()
        )
    if (
        set(actual_mapping) != EXPECTED_STATUSES
        or actual_mapping != EXPECTED_REASON_MAP
    ):
        failures.append("invalid Day 10 status/reason mapping")
    return failures


def validate_migration_order(paths: tuple[Path, ...]) -> list[str]:
    """Require deterministic increasing migration names with Day 9 before Day 11."""

    names = [path.name for path in paths]
    expected = [MIGRATION.name, OUTCOME_MIGRATION.name]
    if names == expected:
        return []
    if names != sorted(names) or names != [path.name for path in HISTORICAL_MIGRATIONS]:
        return ["invalid migration ordering"]
    return []


def validate_historical_migrations(paths: tuple[Path, ...]) -> list[str]:
    """Report incompatible historical assumptions without claiming live safety."""

    names = tuple(path.name for path in paths)
    if names != tuple(path.name for path in HISTORICAL_MIGRATIONS):
        return ["historical migration set is incomplete or unexpected"]
    day9 = paths[0].read_text(encoding="utf-8")
    day19 = paths[1].read_text(encoding="utf-8")
    day11 = paths[2].read_text(encoding="utf-8")
    failures: list[str] = [
        "migration ledger status unknown: live Supabase history was not inspected",
    ]
    if "normalized_plate" in day9 and "plate_number" in day19:
        failures.append(
            "historical schema conflict: Day 9/11 canonical columns conflict with the Day 19 schema"
        )
    if "ocr_status" in day9 and "decision" in day11 and "normalized_plate" in day19:
        failures.append(
            "historical schema conflict: Day 19 cannot safely be applied as the canonical chain"
        )
    return failures


def main() -> int:
    """Validate the retained migration and print a safe local result."""

    try:
        migrations = HISTORICAL_MIGRATIONS
        sql_by_migration = [
            (migration.name, migration.read_text(encoding="utf-8"))
            for migration in migrations
        ]
    except OSError:
        print("Schema validation failed: migration unavailable.", file=sys.stderr)
        return 1
    failures = [
        (name, failure)
        for name, sql in sql_by_migration
        for failure in validate_schema(sql)
    ]
    failures.extend(
        ("migration sequence", failure)
        for failure in validate_migration_order(migrations)
    )
    failures.extend(
        ("migration safety", failure)
        for failure in validate_historical_migrations(migrations)
    )
    if failures:
        for name, failure in failures:
            print(f"Schema validation failed ({name}): {failure}.", file=sys.stderr)
        return 1
    print(
        "Schema validation passed: " + ", ".join(name for name, _ in sql_by_migration)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
