import {
  ApiConfigurationError,
  ApiRequestError,
  buildApiUrl,
  createApiClient,
  normalizeApiBaseUrl,
  resolveApiBaseUrl,
} from "@/lib/api/client";
import type { HealthResponse } from "@/lib/api/types";
import { afterEach, describe, expect, it, vi } from "vitest";

function parseHealth(value: unknown): HealthResponse {
  if (
    !value ||
    typeof value !== "object" ||
    !("status" in value) ||
    value.status !== "ok" ||
    !("service" in value) ||
    typeof value.service !== "string" ||
    !("version" in value) ||
    typeof value.version !== "string"
  ) {
    throw new Error("invalid health response");
  }
  return {
    status: value.status,
    service: value.service,
    version: value.version,
  };
}

describe("frontend API configuration", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("normalizes a public HTTP API origin without exposing credentials", () => {
    expect(normalizeApiBaseUrl("https://api.example.test/v1/")).toBe(
      "https://api.example.test/v1",
    );
  });

  it.each([
    "file:///private/api",
    "https://service-role:fake-secret@example.test",
    "https://example.test?secret=fake-secret",
    "https://example.test/#private",
    "not a URL",
  ])("rejects unsafe API base URL %s", (value) => {
    expect(() => normalizeApiBaseUrl(value)).toThrow(ApiConfigurationError);
  });

  it("uses localhost only as the development/test fallback", () => {
    expect(resolveApiBaseUrl(undefined, "development")).toBe(
      "http://127.0.0.1:8000",
    );
    expect(resolveApiBaseUrl("", "test")).toBe("http://127.0.0.1:8000");
  });

  it("accepts an explicit production API URL", () => {
    expect(
      resolveApiBaseUrl("https://api.example.test/api/v1/", "production"),
    ).toBe("https://api.example.test/api/v1");
  });

  it.each([undefined, "", "   ", "file:///private/api"])(
    "fails closed for missing or invalid production configuration",
    (value) => {
      expect(() => resolveApiBaseUrl(value, "production")).toThrow(
        ApiConfigurationError,
      );
    },
  );

  it("does not call fetch for invalid production configuration", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(() => createApiClient(undefined, 15_000, "production")).toThrow(
      ApiConfigurationError,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([1_000, 60_000])("accepts timeout boundary %s", (timeout) => {
    expect(() =>
      createApiClient("http://127.0.0.1:8000", timeout),
    ).not.toThrow();
  });

  it.each([999, 60_001, 1.5, Number.NaN, true])(
    "rejects unsafe request timeout %s",
    (timeout) => {
      expect(() =>
        createApiClient(
          "http://127.0.0.1:8000",
          timeout as unknown as number,
        ),
      ).toThrow(ApiConfigurationError);
    },
  );
});

describe("API endpoint containment", () => {
  const repeatedlyEncode = (value: string, depth: number) => {
    let encoded = value;
    for (let index = 0; index < depth; index += 1) {
      encoded = encodeURIComponent(encoded);
    }
    return encoded;
  };

  it.each([
    ["/health", "https://example.test/api/v1/health"],
    ["health", "https://example.test/api/v1/health"],
    ["/recognition/validate-image", "https://example.test/api/v1/recognition/validate-image"],
  ])("joins %s beneath a configured base path", (path, expected) => {
    expect(buildApiUrl("https://example.test/api/v1/", path)).toBe(expected);
  });

  it.each([
    "../health",
    "./health",
    "/../health",
    "/%2e%2e/health",
    "/%252e%252e/health",
    `/${repeatedlyEncode(".", 4)}/health`,
    `/${repeatedlyEncode(".", 20)}/health`,
    `/${repeatedlyEncode("..", 12)}/health`,
    `/${repeatedlyEncode("/", 12)}/health`,
    `/${repeatedlyEncode("\\", 12)}/health`,
    "/%2525ZZ/health",
    "/%2E/health",
    "/%2f%2e%2e/health",
    "/health?secret=value",
    "/health#private",
    "//example.test/health",
    "https://evil.example/health",
    "/recognition//health",
    "\\\\evil.example\\health",
  ])("rejects an unsafe or ambiguous endpoint path %s", (path) => {
    expect(() =>
      buildApiUrl("https://example.test/api/v1", path),
    ).toThrow(ApiConfigurationError);
  });

  it("canonicalizes an encoded ordinary character inside the base path", () => {
    expect(
      buildApiUrl("https://example.test/api/v1", "/plates/%2541"),
    ).toBe("https://example.test/api/v1/plates/A");
  });
});

describe("typed API client", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns a runtime-validated success response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ status: "ok", service: "cvpx-api", version: "0.1.0" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await createApiClient(
      "http://127.0.0.1:8000",
    ).request("/health", parseHealth);

    expect(result).toEqual({
      status: "ok",
      service: "cvpx-api",
      version: "0.1.0",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/health",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it.each([
    { status: "ok", service: "cvpx-api" },
    { status: "ok", service: 42, version: "0.1.0" },
    { unexpected: "shape" },
  ])("rejects unexpected successful JSON %#", async (payload) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), { status: 200 }),
      ),
    );

    await expect(
      createApiClient("http://127.0.0.1:8000").request("/health", parseHealth),
    ).rejects.toMatchObject({
      code: "API_RESPONSE_INVALID",
      message: "The API returned an invalid response.",
      status: 200,
    });
  });

  it.each([
    ["malformed JSON", "{private-provider-output", 200],
    ["empty response", "", 200],
  ])("sanitizes %s on success", async (_, body, status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(body, { status })),
    );

    await expect(
      createApiClient("http://127.0.0.1:8000").request("/health", parseHealth),
    ).rejects.toMatchObject({
      code: "API_RESPONSE_INVALID",
      status,
    });
  });

  it("lets an operation explicitly accept a 204 response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );

    const result = await createApiClient(
      "http://127.0.0.1:8000",
    ).request("/health", (value) => {
      if (value !== null) {
        throw new Error("expected empty response");
      }
      return undefined;
    });

    expect(result).toBeUndefined();
  });

  it.each([
    [
      {
        error: {
          code: "IMAGE_INVALID",
          message: "The image is invalid.",
          correlation_id: "11111111-1111-4111-8111-111111111111",
        },
      },
      "11111111-1111-4111-8111-111111111111",
    ],
    [
      {
        error: {
          code: "HTTP_ERROR",
          message: "The request could not be completed.",
        },
      },
      null,
    ],
  ])(
    "preserves an authoritative backend error envelope",
    async (payload, correlationId) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            new Response(JSON.stringify(payload), { status: 400 }),
          ),
      );

      await expect(
        createApiClient("http://127.0.0.1:8000").request(
          "/api/test",
          parseHealth,
        ),
      ).rejects.toMatchObject({
        code: payload.error.code,
        message: payload.error.message,
        status: 400,
        correlationId,
      });
    },
  );

  it.each([
    { detail: { code: "WRONG_ENVELOPE", message: "fake-secret" } },
    { error: { code: 42, message: "fake-secret" } },
    { error: { code: "BROKEN", message: 42 } },
    { error: { code: "BROKEN", message: "safe", correlation_id: 42 } },
  ])("sanitizes malformed provider error payload %#", async (payload) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify(payload), { status: 503 }),
        ),
    );

    await expect(
      createApiClient("http://127.0.0.1:8000").request(
        "/api/test",
        parseHealth,
      ),
    ).rejects.toMatchObject({
      code: "API_REQUEST_FAILED",
      message: "The API request could not be completed.",
      status: 503,
      correlationId: null,
    });
  });

  it("sanitizes a non-JSON provider failure", async () => {
    const secret = "fake-secret C:\\private\\provider.log /srv/private/error";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(secret, { status: 503 })),
    );

    let failure: unknown;
    try {
      await createApiClient("http://127.0.0.1:8000").request(
        "/api/test",
        parseHealth,
      );
    } catch (error) {
      failure = error;
    }

    expect(failure).toBeInstanceOf(ApiRequestError);
    expect(String(failure)).not.toContain(secret);
    expect(failure).toMatchObject({
      code: "API_REQUEST_FAILED",
      status: 503,
      correlationId: null,
    });
  });

  it("sanitizes network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValue(
          new Error("provider fake-secret at C:\\private\\socket.log"),
        ),
    );

    await expect(
      createApiClient("http://127.0.0.1:8000").request(
        "/api/test",
        parseHealth,
      ),
    ).rejects.toMatchObject({
      code: "API_UNAVAILABLE",
      message: "The API is unavailable.",
      status: null,
    });
  });

  it("distinguishes a timer-triggered timeout and clears its timer", async () => {
    vi.useFakeTimers();
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");
    vi.stubGlobal(
      "fetch",
      vi.fn((_: string, init: RequestInit) => {
        return new Promise((_, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("private provider detail", "AbortError")),
          );
        });
      }),
    );

    const request = createApiClient(
      "http://127.0.0.1:8000",
      1_000,
    ).request("/health", parseHealth);
    const rejection = expect(request).rejects.toMatchObject({
      code: "API_REQUEST_TIMEOUT",
      message: "The API request timed out.",
    });
    await vi.advanceTimersByTimeAsync(1_000);

    await rejection;
    expect(clearTimeoutSpy).toHaveBeenCalledOnce();
  });

  it("keeps caller cancellation when fetch settles after the deadline", async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");
    let rejectFetch: ((reason: unknown) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((_, reject) => {
            rejectFetch = reject;
          }),
      ),
    );

    const request = createApiClient(
      "http://127.0.0.1:8000",
      1_000,
    ).request("/health", parseHealth, { signal: caller.signal });
    const rejection = expect(request).rejects.toMatchObject({
      code: "API_REQUEST_CANCELLED",
    });
    caller.abort();
    await vi.advanceTimersByTimeAsync(1_000);
    rejectFetch?.(new DOMException("private provider detail", "AbortError"));

    await rejection;
    expect(clearTimeoutSpy).toHaveBeenCalled();
  });

  it("keeps timeout when caller cancellation occurs before delayed settlement", async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    let rejectFetch: ((reason: unknown) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((_, reject) => {
            rejectFetch = reject;
          }),
      ),
    );

    const request = createApiClient(
      "http://127.0.0.1:8000",
      1_000,
    ).request("/health", parseHealth, { signal: caller.signal });
    const rejection = expect(request).rejects.toMatchObject({
      code: "API_REQUEST_TIMEOUT",
    });
    await vi.advanceTimersByTimeAsync(1_000);
    caller.abort();
    rejectFetch?.(new DOMException("private provider detail", "AbortError"));

    await rejection;
  });

  it("distinguishes caller cancellation and removes the listener", async () => {
    const caller = new AbortController();
    const removeSpy = vi.spyOn(caller.signal, "removeEventListener");
    vi.stubGlobal(
      "fetch",
      vi.fn((_: string, init: RequestInit) => {
        return new Promise((_, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("private provider detail", "AbortError")),
          );
        });
      }),
    );

    const request = createApiClient(
      "http://127.0.0.1:8000",
      60_000,
    ).request("/health", parseHealth, { signal: caller.signal });
    caller.abort();

    await expect(request).rejects.toMatchObject({
      code: "API_REQUEST_CANCELLED",
      message: "The API request was cancelled.",
    });
    expect(removeSpy).toHaveBeenCalledWith("abort", expect.any(Function));
  });

  it("classifies an already-cancelled request without provider detail", async () => {
    const caller = new AbortController();
    caller.abort();
    const fetchMock = vi.fn((_: string, init: RequestInit) => {
      expect(init.signal?.aborted).toBe(true);
      return Promise.reject(new DOMException("private detail", "AbortError"));
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      createApiClient("http://127.0.0.1:8000").request(
        "/health",
        parseHealth,
        { signal: caller.signal },
      ),
    ).rejects.toMatchObject({ code: "API_REQUEST_CANCELLED" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
