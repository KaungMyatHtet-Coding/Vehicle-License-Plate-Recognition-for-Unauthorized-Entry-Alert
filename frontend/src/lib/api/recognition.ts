import { apiClient } from "@/lib/api/client";
import type {
  DecisionReason,
  DecisionStatus,
  DetectionLoggingResult,
  LoggingFailureCode,
  PlateDetection,
  PlateOcrResponse,
  RecognitionResponse,
} from "@/lib/api/types";

const DECISIONS = new Set<DecisionStatus>([
  "AUTHORIZED",
  "UNAUTHORIZED",
  "MANUAL_REVIEW",
]);
const REASONS = new Set<DecisionReason>([
  "ACTIVE_MATCH",
  "OCR_EMPTY",
  "OCR_LOW_CONFIDENCE",
  "OCR_RESULT_INVALID",
  "DECISION_TIME_INVALID",
  "VEHICLE_NOT_FOUND",
  "VEHICLE_INACTIVE",
  "VEHICLE_BLOCKED",
  "VEHICLE_NOT_YET_VALID",
  "VEHICLE_EXPIRED",
  "VEHICLE_RECORD_INVALID",
  "VEHICLE_LOOKUP_FAILED",
]);
const LOGGING_FAILURES = new Set<LoggingFailureCode>([
  "LOG_INPUT_INVALID",
  "LOG_TIME_INVALID",
  "ANNOTATION_FAILED",
  "EVIDENCE_STORAGE_FAILED",
  "EVIDENCE_CONFIRMATION_INVALID",
  "EVIDENCE_ORPHAN_UNVERIFIED",
  "LOG_PERSISTENCE_FAILED",
  "EVIDENCE_CLEANUP_SUCCEEDED",
  "EVIDENCE_CLEANUP_FAILED",
  "SIGNED_ACCESS_FAILED",
]);

type ObjectValue = Record<string, unknown>;

function object(value: unknown): ObjectValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("invalid object");
  }
  return value as ObjectValue;
}

function exact(item: ObjectValue, keys: readonly string[]) {
  if (
    Object.keys(item).length !== keys.length ||
    keys.some((key) => !(key in item))
  ) {
    throw new Error("invalid fields");
  }
}

function string(value: unknown): string {
  if (typeof value !== "string") throw new Error("invalid string");
  return value;
}

function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error("invalid number");
  }
  return value;
}

function nullableString(value: unknown): string | null {
  return value === null ? null : string(value);
}

function plate(value: unknown): PlateDetection {
  const item = object(value);
  exact(item, ["bbox", "confidence", "label", "crop"]);
  const bbox = object(item.bbox);
  exact(bbox, ["x1", "y1", "x2", "y2"]);
  const crop = object(item.crop);
  exact(crop, ["media_type", "base64_data", "width", "height"]);
  const mediaType = string(crop.media_type);
  if (mediaType !== "image/png") throw new Error("invalid crop media type");
  return {
    bbox: {
      x1: number(bbox.x1),
      y1: number(bbox.y1),
      x2: number(bbox.x2),
      y2: number(bbox.y2),
    },
    confidence: number(item.confidence),
    label: string(item.label),
    crop: {
      media_type: mediaType,
      base64_data: string(crop.base64_data),
      width: number(crop.width),
      height: number(crop.height),
    },
  };
}

function ocr(value: unknown): PlateOcrResponse {
  const item = object(value);
  exact(item, [
    "correlation_id",
    "status",
    "review_reason",
    "raw_text",
    "normalized_text",
    "confidence",
    "mode",
    "inference_ms",
    "total_ms",
    "image_width",
    "image_height",
  ]);
  const status = string(item.status);
  const mode = string(item.mode);
  const reviewReason = nullableString(item.review_reason);
  if (
    !["recognized", "manual_review"].includes(status) ||
    !["recognition_only", "full_pipeline"].includes(mode) ||
    (reviewReason !== null &&
      !["OCR_EMPTY", "OCR_LOW_CONFIDENCE", "PLATE_REGION_MISSING", "PLATE_FORMAT_UNSUPPORTED", "PLATE_TEXT_UNRELIABLE", "MULTIPLE_PLATES_AMBIGUOUS"].includes(reviewReason))
  ) {
    throw new Error("invalid OCR state");
  }
  const confidence =
    item.confidence === null ? null : number(item.confidence);
  if (confidence !== null && confidence > 1) throw new Error("invalid confidence");
  return {
    correlation_id: string(item.correlation_id),
    status: status as PlateOcrResponse["status"],
    review_reason: reviewReason as PlateOcrResponse["review_reason"],
    raw_text: string(item.raw_text),
    normalized_text: string(item.normalized_text),
    confidence,
    mode: mode as PlateOcrResponse["mode"],
    inference_ms: number(item.inference_ms),
    total_ms: number(item.total_ms),
    image_width: number(item.image_width),
    image_height: number(item.image_height),
  };
}

function logging(value: unknown): DetectionLoggingResult {
  const item = object(value);
  exact(item, [
    "decision",
    "status",
    "failures",
    "log_persisted",
    "evidence_available",
    "completed_at",
  ]);
  const decision = object(item.decision);
  exact(decision, [
    "correlation_id",
    "decision",
    "reason",
    "message",
    "normalized_plate",
    "confidence",
    "vehicle_id",
    "evaluated_at",
  ]);
  const decisionStatus = string(decision.decision) as DecisionStatus;
  const reason = string(decision.reason) as DecisionReason;
  const failures = item.failures;
  const status = string(item.status);
  if (
    !DECISIONS.has(decisionStatus) ||
    !REASONS.has(reason) ||
    !Array.isArray(failures) ||
    failures.some(
      (failure) =>
        typeof failure !== "string" ||
        !LOGGING_FAILURES.has(failure as LoggingFailureCode),
    ) ||
    !["completed", "partial_failure"].includes(status) ||
    typeof item.log_persisted !== "boolean"
  ) {
    throw new Error("invalid logging state");
  }
  if (typeof item.evidence_available !== "boolean") {
    throw new Error("invalid evidence state");
  }
  const confidence =
    decision.confidence === null ? null : number(decision.confidence);
  if (confidence !== null && confidence > 1) throw new Error("invalid confidence");
  return {
    decision: {
      correlation_id: string(decision.correlation_id),
      decision: decisionStatus,
      reason,
      message: string(decision.message),
      normalized_plate: string(decision.normalized_plate),
      confidence,
      vehicle_id: nullableString(decision.vehicle_id),
      evaluated_at: string(decision.evaluated_at),
    },
    status: status as DetectionLoggingResult["status"],
    failures: failures as LoggingFailureCode[],
    log_persisted: item.log_persisted,
    evidence_available: item.evidence_available,
    completed_at: string(item.completed_at),
  };
}

export function parseRecognitionResponse(value: unknown): RecognitionResponse {
  const item = object(value);
  exact(item, [
    "correlation_id",
    "status",
    "message",
    "detection_count",
    "selected_plate",
    "ocr",
    "logging",
    "timings",
  ]);
  const status = string(item.status);
  const timings = object(item.timings);
  exact(timings, ["detection_ms", "ocr_ms", "total_ms"]);
  if (!["no_plate_detected", "completed"].includes(status)) {
    throw new Error("invalid recognition status");
  }
  const result: RecognitionResponse = {
    correlation_id: string(item.correlation_id),
    status: status as RecognitionResponse["status"],
    message: string(item.message),
    detection_count: number(item.detection_count),
    selected_plate: item.selected_plate === null ? null : plate(item.selected_plate),
    ocr: item.ocr === null ? null : ocr(item.ocr),
    logging: item.logging === null ? null : logging(item.logging),
    timings: {
      detection_ms: number(timings.detection_ms),
      ocr_ms: number(timings.ocr_ms),
      total_ms: number(timings.total_ms),
    },
  };
  const noPlateIsConsistent =
    result.status === "no_plate_detected" &&
    result.detection_count === 0 &&
    result.selected_plate === null &&
    result.ocr === null &&
    result.logging === null;
  const completedIsConsistent =
    result.status === "completed" &&
    result.detection_count >= 1 &&
    result.selected_plate !== null &&
    result.ocr !== null &&
    result.logging !== null &&
    result.correlation_id === result.ocr.correlation_id &&
    result.correlation_id === result.logging.decision.correlation_id;
  if (!noPlateIsConsistent && !completedIsConsistent) {
    throw new Error("inconsistent recognition response");
  }
  return result;
}

export async function analyzeVehicleImage(
  file: File,
  signal?: AbortSignal,
): Promise<RecognitionResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  return apiClient.request("/api/recognition/analyze", parseRecognitionResponse, {
    method: "POST",
    body: form,
    signal,
  });
}
