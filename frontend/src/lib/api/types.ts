export interface HealthResponse {
  readonly status: "ok";
  readonly service: string;
  readonly version: string;
}

export interface ApiErrorBody {
  readonly code: string;
  readonly message: string;
  readonly correlation_id?: string;
}

export interface ApiErrorResponse {
  readonly error: ApiErrorBody;
}

export interface ImageValidationResponse {
  readonly correlation_id: string;
  readonly filename: string;
  readonly content_type: string;
  readonly detected_format: string;
  readonly size_bytes: number;
  readonly width: number;
  readonly height: number;
}

export interface BoundingBox {
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
}

export interface PlateCrop {
  readonly media_type: string;
  readonly base64_data: string;
  readonly width: number;
  readonly height: number;
}

export interface PlateDetection {
  readonly bbox: BoundingBox;
  readonly confidence: number;
  readonly label: string;
  readonly crop: PlateCrop;
}

export interface ImageDetectionResponse {
  readonly correlation_id: string;
  readonly status: string;
  readonly detection_count: number;
  readonly image_width: number;
  readonly image_height: number;
  readonly inference_ms: number;
  readonly total_ms: number;
  readonly detections: ReadonlyArray<PlateDetection>;
}

export type OcrStatus = "recognized" | "manual_review";
export type OcrReviewReason = "OCR_EMPTY" | "OCR_LOW_CONFIDENCE";

export interface PlateOcrResponse {
  readonly correlation_id: string;
  readonly status: OcrStatus;
  readonly review_reason: OcrReviewReason | null;
  readonly raw_text: string;
  readonly normalized_text: string;
  readonly confidence: number | null;
  readonly mode: "recognition_only" | "full_pipeline";
  readonly inference_ms: number;
  readonly total_ms: number;
  readonly image_width: number;
  readonly image_height: number;
}

export type DecisionStatus =
  | "AUTHORIZED"
  | "UNAUTHORIZED"
  | "MANUAL_REVIEW";

export type DecisionReason =
  | "ACTIVE_MATCH"
  | "OCR_EMPTY"
  | "OCR_LOW_CONFIDENCE"
  | "OCR_RESULT_INVALID"
  | "DECISION_TIME_INVALID"
  | "VEHICLE_NOT_FOUND"
  | "VEHICLE_INACTIVE"
  | "VEHICLE_BLOCKED"
  | "VEHICLE_NOT_YET_VALID"
  | "VEHICLE_EXPIRED"
  | "VEHICLE_RECORD_INVALID"
  | "VEHICLE_LOOKUP_FAILED";

export interface DecisionAuditSnapshot {
  readonly correlation_id: string;
  readonly decision: DecisionStatus;
  readonly reason: DecisionReason;
  readonly message: string;
  readonly normalized_plate: string;
  readonly confidence: number | null;
  readonly vehicle_id: string | null;
  readonly evaluated_at: string;
}

export type LoggingFailureCode =
  | "LOG_INPUT_INVALID"
  | "LOG_TIME_INVALID"
  | "ANNOTATION_FAILED"
  | "EVIDENCE_STORAGE_FAILED"
  | "EVIDENCE_CONFIRMATION_INVALID"
  | "EVIDENCE_ORPHAN_UNVERIFIED"
  | "LOG_PERSISTENCE_FAILED"
  | "EVIDENCE_CLEANUP_SUCCEEDED"
  | "EVIDENCE_CLEANUP_FAILED"
  | "SIGNED_ACCESS_FAILED";

export interface EvidenceReference {
  readonly bucket: string;
  readonly object_path: string;
}

export interface SignedEvidenceAccess {
  readonly token: string;
  readonly expires_at: string;
}

export interface DetectionLoggingResult {
  readonly decision: DecisionAuditSnapshot;
  readonly status: "completed" | "partial_failure";
  readonly failures: ReadonlyArray<LoggingFailureCode>;
  readonly log_persisted: boolean;
  readonly evidence: EvidenceReference | null;
  readonly signed_access: SignedEvidenceAccess | null;
  readonly completed_at: string;
}
