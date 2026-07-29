begin;

alter table public.detection_logs
    add column decision text,
    add column decision_reason text,
    add column matched_vehicle_id uuid;

update public.detection_logs
set
    decision = 'MANUAL_REVIEW',
    decision_reason = case
        when review_reason = 'OCR_EMPTY' then 'OCR_EMPTY'
        when review_reason = 'OCR_LOW_CONFIDENCE' then 'OCR_LOW_CONFIDENCE'
        else 'OCR_RESULT_INVALID'
    end;

alter table public.detection_logs
    alter column decision set not null,
    alter column decision_reason set not null,
    add constraint detection_logs_decision_reason
        check (
            (decision = 'AUTHORIZED' and decision_reason = 'ACTIVE_MATCH')
            or (
                decision = 'UNAUTHORIZED'
                and decision_reason in (
                    'VEHICLE_NOT_FOUND',
                    'VEHICLE_INACTIVE',
                    'VEHICLE_BLOCKED',
                    'VEHICLE_NOT_YET_VALID',
                    'VEHICLE_EXPIRED'
                )
            )
            or (
                decision = 'MANUAL_REVIEW'
                and decision_reason in (
                    'OCR_EMPTY',
                    'OCR_LOW_CONFIDENCE',
                    'OCR_RESULT_INVALID',
                    'DECISION_TIME_INVALID',
                    'VEHICLE_RECORD_INVALID',
                    'VEHICLE_LOOKUP_FAILED'
                )
            )
        ),
    add constraint detection_logs_authorized_vehicle
        check (decision <> 'AUTHORIZED' or matched_vehicle_id is not null),
    add constraint detection_logs_matched_vehicle_fk
        foreign key (matched_vehicle_id)
        references public.authorized_vehicles (id)
        on delete restrict;

create index detection_logs_decision_created_at_idx
    on public.detection_logs (decision, created_at desc);

commit;
