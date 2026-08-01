import type { ApiErrorResponse } from "@/lib/api/types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_MS = 15_000;
const MIN_TIMEOUT_MS = 1_000;
const MAX_TIMEOUT_MS = 60_000;

export type ResponseParser<T> = (value: unknown) => T;

export class ApiConfigurationError extends Error {
  readonly code = "API_CONFIGURATION_INVALID";

  constructor() {
    super("The frontend API configuration is invalid.");
    this.name = "ApiConfigurationError";
  }
}

export class ApiRequestError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number | null,
    readonly correlationId: string | null,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function isProduction(environment: string | undefined): boolean {
  return environment === "production";
}

export function resolveApiBaseUrl(
  configuredValue: string | undefined,
  environment = process.env.NODE_ENV,
): string {
  if (configuredValue === undefined || configuredValue.trim() === "") {
    if (isProduction(environment)) {
      throw new ApiConfigurationError();
    }
    return DEFAULT_API_BASE_URL;
  }
  return normalizeApiBaseUrl(configuredValue);
}

export function normalizeApiBaseUrl(value: string): string {
  try {
    const parsed = new URL(value);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.search ||
      parsed.hash
    ) {
      throw new ApiConfigurationError();
    }
    return `${parsed.origin}${parsed.pathname.replace(/\/+$/, "")}`;
  } catch {
    throw new ApiConfigurationError();
  }
}

function isApiErrorResponse(value: unknown): value is ApiErrorResponse {
  if (!value || typeof value !== "object" || !("error" in value)) {
    return false;
  }
  const error = value.error;
  return (
    !!error &&
    typeof error === "object" &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string" &&
    (!("correlation_id" in error) ||
      typeof error.correlation_id === "string")
  );
}

function normalizeEndpointSegment(segment: string): string {
  let decoded = segment;
  let reachedFixedPoint = false;
  // Each changing decode consumes at least one finite %XX sequence. The
  // original character count therefore safely bounds every meaningful layer.
  const maximumPasses = segment.length + 1;
  try {
    for (let pass = 0; pass < maximumPasses; pass += 1) {
      const next = decodeURIComponent(decoded);
      if (next === decoded) {
        reachedFixedPoint = true;
        break;
      }
      decoded = next;
    }
  } catch {
    throw new ApiConfigurationError();
  }
  if (
    !reachedFixedPoint ||
    decoded === "." ||
    decoded === ".." ||
    decoded.includes("/") ||
    decoded.includes("\\")
  ) {
    throw new ApiConfigurationError();
  }
  return encodeURIComponent(decoded);
}

export function buildApiUrl(baseUrl: string, endpointPath: string): string {
  if (
    !endpointPath ||
    endpointPath.includes("?") ||
    endpointPath.includes("#") ||
    endpointPath.includes("\\") ||
    endpointPath.startsWith("//") ||
    endpointPath.includes("://") ||
    endpointPath.includes("//")
  ) {
    throw new ApiConfigurationError();
  }

  const relativePath = endpointPath.startsWith("/")
    ? endpointPath.slice(1)
    : endpointPath;
  const segments = relativePath.split("/");
  if (segments.some((segment) => segment.length === 0)) {
    throw new ApiConfigurationError();
  }
  const normalizedSegments = segments.map(normalizeEndpointSegment);

  const normalizedBase = normalizeApiBaseUrl(baseUrl);
  const base = new URL(`${normalizedBase}/`);
  const result = new URL(normalizedSegments.join("/"), base);
  const requiredPrefix = `${base.pathname.replace(/\/+$/, "")}/`;
  if (
    result.origin !== base.origin ||
    !result.pathname.startsWith(requiredPrefix) ||
    result.search ||
    result.hash
  ) {
    throw new ApiConfigurationError();
  }
  return result.toString();
}

export function createApiClient(
  configuredBaseUrl: string | undefined = process.env.NEXT_PUBLIC_API_BASE_URL,
  requestTimeoutMs = DEFAULT_TIMEOUT_MS,
  environment = process.env.NODE_ENV,
) {
  const baseUrl = resolveApiBaseUrl(configuredBaseUrl, environment);
  if (
    !Number.isInteger(requestTimeoutMs) ||
    requestTimeoutMs < MIN_TIMEOUT_MS ||
    requestTimeoutMs > MAX_TIMEOUT_MS
  ) {
    throw new ApiConfigurationError();
  }

  return {
    async request<T>(
      path: string,
      parse: ResponseParser<T>,
      init: RequestInit = {},
      query: Readonly<Record<string, string>> = {},
    ): Promise<T> {
      const requestUrl = new URL(buildApiUrl(baseUrl, path));
      for (const [key, value] of Object.entries(query)) {
        if (!/^[a-z][a-z0-9_]*$/.test(key) || typeof value !== "string") {
          throw new ApiConfigurationError();
        }
        requestUrl.searchParams.set(key, value);
      }
      const controller = new AbortController();
      let abortCause: "caller" | "timeout" | null = null;
      const timeout = setTimeout(() => {
        if (abortCause === null) {
          abortCause = "timeout";
          controller.abort();
        }
      }, requestTimeoutMs);
      const abortFromCaller = () => {
        if (abortCause === null) {
          abortCause = "caller";
          clearTimeout(timeout);
          controller.abort();
        }
      };
      init.signal?.addEventListener("abort", abortFromCaller, { once: true });
      if (init.signal?.aborted) {
        abortFromCaller();
      }

      try {
        const response = await fetch(requestUrl.toString(), {
          ...init,
          headers: {
            Accept: "application/json",
            ...init.headers,
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          let payload: unknown = null;
          try {
            payload = await response.json();
          } catch {
            // A non-JSON provider response is deliberately not exposed.
          }
          if (isApiErrorResponse(payload)) {
            throw new ApiRequestError(
              payload.error.code,
              payload.error.message,
              response.status,
              payload.error.correlation_id ?? null,
            );
          }
          throw new ApiRequestError(
            "API_REQUEST_FAILED",
            "The API request could not be completed.",
            response.status,
            null,
          );
        }

        let payload: unknown;
        if (response.status === 204) {
          payload = null;
        } else {
          try {
            const body = await response.text();
            payload = body === "" ? null : JSON.parse(body);
          } catch {
            throw new ApiRequestError(
              "API_RESPONSE_INVALID",
              "The API returned an invalid response.",
              response.status,
              null,
            );
          }
        }
        try {
          return parse(payload);
        } catch {
          throw new ApiRequestError(
            "API_RESPONSE_INVALID",
            "The API returned an invalid response.",
            response.status,
            null,
          );
        }
      } catch (error) {
        if (error instanceof ApiRequestError) {
          throw error;
        }
        if (abortCause === "timeout") {
          throw new ApiRequestError(
            "API_REQUEST_TIMEOUT",
            "The API request timed out.",
            null,
            null,
          );
        }
        if (abortCause === "caller") {
          throw new ApiRequestError(
            "API_REQUEST_CANCELLED",
            "The API request was cancelled.",
            null,
            null,
          );
        }
        throw new ApiRequestError(
          "API_UNAVAILABLE",
          "The API is unavailable.",
          null,
          null,
        );
      } finally {
        clearTimeout(timeout);
        init.signal?.removeEventListener("abort", abortFromCaller);
      }
    },
  };
}

export const apiClient = {
  request<T>(
    path: string,
    parse: ResponseParser<T>,
    init: RequestInit = {},
    query: Readonly<Record<string, string>> = {},
  ): Promise<T> {
    return createApiClient().request(path, parse, init, query);
  },
};
