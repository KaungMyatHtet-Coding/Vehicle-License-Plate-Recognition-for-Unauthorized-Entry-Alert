begin;

create extension if not exists pgcrypto;

create or replace function public.is_nonnegative_finite_timings(value jsonb)
returns boolean
language sql
immutable
set search_path = ''
as $$
    select
        jsonb_typeof(value) = 'object'
        and not exists (
            select 1
            from jsonb_each(value) as item
            where jsonb_typeof(item.value) <> 'number'
                or (item.value #>> '{}')::numeric < 0
        );
$$;

create table public.authorized_vehicles (
    id uuid primary key default gen_random_uuid(),
    normalized_plate text not null,
    status text not null default 'active'
        check (status in ('active', 'inactive', 'blocked')),
    description text,
    valid_from timestamptz,
    valid_until timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint authorized_vehicles_normalized_plate_format
        check (
            normalized_plate ~ '^[A-Z0-9]+$'
            and normalized_plate =
                upper(regexp_replace(normalized_plate, '[^A-Z0-9]', '', 'g'))
        ),
    constraint authorized_vehicles_validity_order
        check (
            valid_from is null
            or valid_until is null
            or valid_until > valid_from
        ),
    constraint authorized_vehicles_normalized_plate_unique
        unique (normalized_plate)
);

create index authorized_vehicles_status_validity_idx
    on public.authorized_vehicles (status, valid_from, valid_until);

create table public.detection_logs (
    id uuid primary key default gen_random_uuid(),
    correlation_id uuid not null unique,
    raw_text text not null default '',
    normalized_text text not null default '',
    confidence double precision
        check (confidence is null or confidence between 0.0 and 1.0),
    ocr_status text not null
        check (ocr_status in ('recognized', 'manual_review')),
    review_reason text
        check (
            review_reason is null
            or review_reason in ('OCR_EMPTY', 'OCR_LOW_CONFIDENCE')
        ),
    evidence_bucket text,
    evidence_object_path text,
    timings jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint detection_logs_normalized_text_format
        check (
            normalized_text = ''
            or normalized_text ~ '^[A-Z0-9]+$'
        ),
    constraint detection_logs_ocr_state
        check (
            (ocr_status = 'recognized' and review_reason is null)
            or (
                ocr_status = 'manual_review'
                and review_reason in ('OCR_EMPTY', 'OCR_LOW_CONFIDENCE')
            )
        ),
    constraint detection_logs_evidence_pair
        check (
            (evidence_bucket is null and evidence_object_path is null)
            or (
                evidence_bucket is not null
                and evidence_object_path is not null
                and evidence_bucket ~ '^[a-z0-9][a-z0-9._-]{0,99}$'
                and length(evidence_object_path) between 1 and 1024
                and evidence_object_path !~ '(^/|\\|(^|/)\.\.(/|$)|^[A-Za-z]:)'
            )
        ),
    constraint detection_logs_timings_object
        check (public.is_nonnegative_finite_timings(timings))
);

create index detection_logs_created_at_idx
    on public.detection_logs (created_at desc);

create index detection_logs_normalized_text_created_at_idx
    on public.detection_logs (normalized_text, created_at desc);

create table public.app_settings (
    key text primary key
        check (key ~ '^[a-z][a-z0-9_.-]{0,99}$'),
    value jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger authorized_vehicles_set_updated_at
before update on public.authorized_vehicles
for each row execute function public.set_updated_at();

create trigger app_settings_set_updated_at
before update on public.app_settings
for each row execute function public.set_updated_at();

alter table public.authorized_vehicles enable row level security;
alter table public.detection_logs enable row level security;
alter table public.app_settings enable row level security;

revoke all on table public.authorized_vehicles from anon, authenticated;
revoke all on table public.detection_logs from anon, authenticated;
revoke all on table public.app_settings from anon, authenticated;

commit;
