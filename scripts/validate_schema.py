"""Offline structural validation for the versioned Day 9 PostgreSQL migration."""

from __future__ import annotations

import re
import sys
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "202607310001_day9_data_model.sql"
)

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
    "Day 10 decision": r"(?i)\b(unauthorized|decision_status|decision_reason)\b",
}


def validate_schema(sql: str) -> list[str]:
    """Return deterministic validation failures without database or network access."""

    normalized = re.sub(r"--[^\n]*", "", sql).strip()
    failures = [
        f"missing {name}"
        for name, pattern in REQUIRED_PATTERNS.items()
        if re.search(pattern, normalized, flags=re.DOTALL | re.IGNORECASE) is None
    ]
    failures.extend(
        f"forbidden {name}"
        for name, pattern in FORBIDDEN_PATTERNS.items()
        if re.search(pattern, normalized) is not None
    )
    if normalized.count("(") != normalized.count(")"):
        failures.append("unbalanced parentheses")
    if "$$" in normalized and normalized.count("$$") % 2:
        failures.append("unbalanced dollar quoting")
    return failures


def main() -> int:
    """Validate the retained migration and print a safe local result."""

    try:
        sql = MIGRATION.read_text(encoding="utf-8")
    except OSError:
        print("Schema validation failed: migration unavailable.", file=sys.stderr)
        return 1
    failures = validate_schema(sql)
    if failures:
        for failure in failures:
            print(f"Schema validation failed: {failure}.", file=sys.stderr)
        return 1
    print(f"Schema validation passed: {MIGRATION.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
