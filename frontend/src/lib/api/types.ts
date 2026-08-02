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

export interface DetectionLoggingResult {
  readonly decision: DecisionAuditSnapshot;
  readonly status: "completed" | "partial_failure";
  readonly failures: ReadonlyArray<LoggingFailureCode>;
  readonly log_persisted: boolean;
  readonly evidence_available: boolean;
  readonly completed_at: string;
}

export interface DetectionSummary {
  readonly correlation_id: string;
  readonly decision: DecisionStatus;
  readonly reason: DecisionReason;
  readonly reason_message: string;
  readonly normalized_plate: string;
  readonly confidence: number | null;
  readonly created_at: string;
  readonly evidence_available: boolean;
}

export interface DetectionDetail extends DetectionSummary {
  readonly timings: Readonly<Record<string, number>>;
  readonly evidence_access: "restricted";
}

export interface PaginatedDetections {
  readonly items: ReadonlyArray<DetectionSummary>;
  readonly page: number;
  readonly page_size: number;
  readonly total_items: number;
  readonly total_pages: number;
  readonly timezone: "UTC";
}

export interface TrendBucket {
  readonly bucket_start: string;
  readonly authorized: number;
  readonly unauthorized: number;
  readonly manual_review: number;
  readonly no_plate: number;
  readonly total: number;
}

export interface DashboardStatistics {
  readonly total_recognitions: number;
  readonly authorized: number;
  readonly unauthorized: number;
  readonly manual_review: number;
  readonly no_plate: number;
  readonly timezone: "UTC";
  readonly trend_granularity: "day";
  readonly trend: ReadonlyArray<TrendBucket>;
}

export interface AlertSummary extends DetectionSummary {
  readonly alert_type: "ENTRY_NOT_AUTHORIZED";
  readonly message: string;
}

export interface PaginatedAlerts {
  readonly items: ReadonlyArray<AlertSummary>;
  readonly page: number;
  readonly page_size: number;
  readonly total_items: number;
  readonly total_pages: number;
  readonly timezone: "UTC";
}

export interface RecognitionTimings {
  readonly detection_ms: number;
  readonly ocr_ms: number;
  readonly total_ms: number;
}

export interface RecognitionResponse {
  readonly correlation_id: string;
  readonly status: "no_plate_detected" | "completed";
  readonly message: string;
  readonly detection_count: number;
  readonly selected_plate: PlateDetection | null;
  readonly ocr: PlateOcrResponse | null;
  readonly logging: DetectionLoggingResult | null;
  readonly timings: RecognitionTimings;
}

export type VehicleStatus = "ACTIVE" | "INACTIVE" | "BLOCKED";

export interface AuthorizedVehicle {
  readonly id: string;
  readonly normalized_plate: string;
  readonly description: string | null;
  readonly status: VehicleStatus;
  readonly valid_from: string | null;
  readonly valid_until: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface AuthorizedVehicleList {
  readonly items: ReadonlyArray<AuthorizedVehicle>;
  readonly total_items: number;
}

export interface VehicleWrite {
  readonly plate_number: string;
  readonly description: string | null;
  readonly status: VehicleStatus;
  readonly valid_from: string | null;
  readonly valid_until: string | null;
}
