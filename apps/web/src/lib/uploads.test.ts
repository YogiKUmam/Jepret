import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./api";
import {
  UploadCancelledError,
  putSignedFile,
  uploadBookingFile,
} from "./uploads";

class FakeXMLHttpRequest {
  static instances: FakeXMLHttpRequest[] = [];
  static throwAt: "constructor" | "open" | "header" | "send" | null = null;
  readonly headers = new Map<string, string>();
  readonly upload = {
    onprogress: null as ((event: ProgressEvent) => void) | null,
  };
  method = "";
  url = "";
  body: Document | XMLHttpRequestBodyInit | null = null;
  status = 0;
  withCredentials = false;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    if (FakeXMLHttpRequest.throwAt === "constructor") {
      throw new DOMException("https://storage.test/?secret=constructor");
    }
    FakeXMLHttpRequest.instances.push(this);
  }

  open(method: string, url: string) {
    if (FakeXMLHttpRequest.throwAt === "open") {
      throw new DOMException(`${url}&secret=open`);
    }
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string) {
    if (FakeXMLHttpRequest.throwAt === "header") {
      throw new DOMException("https://storage.test/?secret=header");
    }
    this.headers.set(name, value);
  }

  send(body: Document | XMLHttpRequestBodyInit | null) {
    if (FakeXMLHttpRequest.throwAt === "send") {
      throw new DOMException("https://storage.test/?secret=send");
    }
    this.body = body;
  }

  abort() {
    this.onabort?.();
  }

  progress(loaded: number, total: number) {
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded,
      total,
    } as ProgressEvent);
  }

  succeed(status = 200) {
    this.status = status;
    this.onload?.();
  }

  fail() {
    this.onerror?.();
  }
}

function response(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve({ data }),
  };
}

beforeEach(() => {
  FakeXMLHttpRequest.instances = [];
  FakeXMLHttpRequest.throwAt = null;
  vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("preserves Headers entries, signal, and an explicit content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const headers = new Headers({
      "Content-Type": "application/custom",
      "X-Request-Id": "request-1",
    });

    await apiFetch("/test", {
      method: "PATCH",
      headers,
      signal: controller.signal,
    });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("PATCH");
    expect(init.signal).toBe(controller.signal);
    expect(Object.fromEntries((init.headers as Headers).entries())).toEqual({
      "content-type": "application/custom",
      "x-request-id": "request-1",
    });
  });
});

describe("putSignedFile", () => {
  it("uploads directly with only signed headers and bounded progress", async () => {
    const progress = vi.fn();
    const controller = new AbortController();
    const file = new File(["payload"], "hasil.png", { type: "image/png" });

    const promise = putSignedFile(
      "https://storage.test/private?secret=do-not-leak",
      file,
      progress,
      controller.signal,
      { "Content-Type": "image/png", "If-None-Match": "*" },
    );
    const xhr = FakeXMLHttpRequest.instances[0];
    xhr.progress(2, 8);
    xhr.progress(20, 8);
    xhr.succeed(200);
    await promise;

    expect(xhr.method).toBe("PUT");
    expect(xhr.withCredentials).toBe(false);
    expect(Object.fromEntries(xhr.headers)).toEqual({
      "Content-Type": "image/png",
      "If-None-Match": "*",
    });
    expect(xhr.headers.has("Authorization")).toBe(false);
    expect(xhr.headers.has("Cookie")).toBe(false);
    expect(progress.mock.calls.flat()).toEqual([0, 25, 100, 100]);
  });

  it("cancels an active request with a stable cancellation error", async () => {
    const controller = new AbortController();
    const promise = putSignedFile(
      "https://storage.test/private?secret=do-not-leak",
      new File(["x"], "hasil.png", { type: "image/png" }),
      vi.fn(),
      controller.signal,
      { "Content-Type": "image/png", "If-None-Match": "*" },
    );

    controller.abort();

    await expect(promise).rejects.toBeInstanceOf(UploadCancelledError);
    await expect(promise).rejects.not.toThrow("do-not-leak");
  });

  it("lets abort win over a queued successful load", async () => {
    const controller = new AbortController();
    const promise = putSignedFile(
      "https://storage.test/private?secret=do-not-leak",
      new File(["x"], "hasil.png", { type: "image/png" }),
      vi.fn(),
      controller.signal,
      { "Content-Type": "image/png", "If-None-Match": "*" },
    );
    const xhr = FakeXMLHttpRequest.instances[0];

    controller.abort();
    xhr.succeed(200);

    await expect(promise).rejects.toBeInstanceOf(UploadCancelledError);
  });

  it("handles an abort fired while the listener is being registered", async () => {
    const controller = new AbortController();
    const originalAdd = controller.signal.addEventListener.bind(
      controller.signal,
    );
    vi.spyOn(controller.signal, "addEventListener").mockImplementation(
      (type, listener, options) => {
        originalAdd(type, listener, options);
        if (type === "abort") controller.abort();
      },
    );

    await expect(
      putSignedFile(
        "https://storage.test/private?secret=do-not-leak",
        new File(["x"], "hasil.png", { type: "image/png" }),
        vi.fn(),
        controller.signal,
        { "Content-Type": "image/png", "If-None-Match": "*" },
      ),
    ).rejects.toBeInstanceOf(UploadCancelledError);
    expect(FakeXMLHttpRequest.instances).toHaveLength(0);
  });

  it("rejects an already-aborted signal without creating an XHR", async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(
      putSignedFile(
        "https://storage.test/private?secret=do-not-leak",
        new File(["x"], "hasil.png", { type: "image/png" }),
        vi.fn(),
        controller.signal,
        { "Content-Type": "image/png", "If-None-Match": "*" },
      ),
    ).rejects.toMatchObject({ code: "UPLOAD_CANCELLED" });
    expect(FakeXMLHttpRequest.instances).toHaveLength(0);
  });

  it("rejects a signed PUT unless both required headers are present", async () => {
    await expect(
      putSignedFile(
        "https://storage.test/private?secret=do-not-leak",
        new File(["x"], "hasil.png", { type: "image/png" }),
        vi.fn(),
        new AbortController().signal,
        { "Content-Type": "image/png" },
      ),
    ).rejects.toThrow("UPLOAD_FAILED");
    expect(FakeXMLHttpRequest.instances).toHaveLength(0);
  });

  it("maps network and HTTP failures without exposing the signed URL", async () => {
    const url = "https://storage.test/private?secret=do-not-leak";
    const first = putSignedFile(
      url,
      new File(["x"], "hasil.png", { type: "image/png" }),
      vi.fn(),
      new AbortController().signal,
      { "Content-Type": "image/png", "If-None-Match": "*" },
    );
    FakeXMLHttpRequest.instances[0].succeed(403);
    await expect(first).rejects.toThrow("UPLOAD_FAILED");
    await expect(first).rejects.not.toThrow(url);

    const second = putSignedFile(
      url,
      new File(["x"], "hasil.png", { type: "image/png" }),
      vi.fn(),
      new AbortController().signal,
      { "Content-Type": "image/png", "If-None-Match": "*" },
    );
    FakeXMLHttpRequest.instances[1].fail();
    await expect(second).rejects.toThrow("UPLOAD_FAILED");
  });

  it.each(["constructor", "open", "header", "send"] as const)(
    "normalizes a synchronous %s exception without leaking the URL",
    async (stage) => {
      FakeXMLHttpRequest.throwAt = stage;
      const promise = putSignedFile(
        "https://storage.test/private?secret=do-not-leak",
        new File(["x"], "hasil.png", { type: "image/png" }),
        vi.fn(),
        new AbortController().signal,
        { "Content-Type": "image/png", "If-None-Match": "*" },
      );

      await expect(promise).rejects.toThrow("UPLOAD_FAILED");
      await expect(promise).rejects.not.toThrow("secret=");
    },
  );

  it("normalizes a progress callback exception and ignores later events", async () => {
    const progress = vi.fn((percent: number) => {
      if (percent === 25) {
        throw new Error("https://storage.test/?secret=progress");
      }
    });
    const promise = putSignedFile(
      "https://storage.test/private?secret=do-not-leak",
      new File(["x"], "hasil.png", { type: "image/png" }),
      progress,
      new AbortController().signal,
      { "Content-Type": "image/png", "If-None-Match": "*" },
    );
    const xhr = FakeXMLHttpRequest.instances[0];
    xhr.progress(1, 4);
    xhr.succeed(200);

    await expect(promise).rejects.toThrow("UPLOAD_FAILED");
    await expect(promise).rejects.not.toThrow("secret=");
  });
});

describe("uploadBookingFile", () => {
  it.each([
    {
      name: "an empty file",
      purpose: "deliverable" as const,
      file: () => new File([], "hasil.png", { type: "image/png" }),
    },
    {
      name: "an unsupported content type",
      purpose: "deliverable" as const,
      file: () =>
        new File(["payload"], "hasil.exe", {
          type: "application/x-msdownload",
        }),
    },
    {
      name: "a zip chat attachment",
      purpose: "chat_attachment" as const,
      file: () =>
        new File(["payload"], "hasil.zip", { type: "application/zip" }),
    },
    {
      name: "a non-plain filename",
      purpose: "deliverable" as const,
      file: () =>
        new File(["payload"], "folder/hasil.png", { type: "image/png" }),
    },
    {
      name: "a filename longer than the API boundary",
      purpose: "deliverable" as const,
      file: () =>
        new File(["payload"], `${"x".repeat(252)}.png`, {
          type: "image/png",
        }),
    },
    {
      name: "an oversized chat attachment",
      purpose: "chat_attachment" as const,
      file: () => {
        const file = new File(["payload"], "hasil.png", { type: "image/png" });
        Object.defineProperty(file, "size", { value: 10 * 1024 * 1024 + 1 });
        return file;
      },
    },
  ])(
    "rejects $name locally before creating an intent",
    async ({ purpose, file }) => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);

      await expect(
        uploadBookingFile({
          bookingId: "booking-1",
          file: file(),
          purpose,
          onProgress: vi.fn(),
          signal: new AbortController().signal,
        }),
      ).rejects.toMatchObject({ code: "UPLOAD_VALIDATION_FAILED" });
      expect(fetchMock).not.toHaveBeenCalled();
      expect(FakeXMLHttpRequest.instances).toHaveLength(0);
    },
  );

  it("cancels during intent creation without starting XHR or completion", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn((_url: string, init: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const promise = uploadBookingFile({
      bookingId: "booking-1",
      file: new File(["payload"], "hasil.png", { type: "image/png" }),
      purpose: "deliverable",
      onProgress: vi.fn(),
      signal: controller.signal,
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    controller.abort();

    await expect(promise).rejects.toBeInstanceOf(UploadCancelledError);
    expect(FakeXMLHttpRequest.instances).toHaveLength(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("cancels during the signed PUT without calling completion", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      response(
        {
          id: "upload-1",
          purpose: "deliverable",
          filename: "hasil.png",
          content_type: "image/png",
          size_bytes: 7,
          status: "pending",
          completed_at: null,
          expires_at: "2026-08-25T12:00:00Z",
          upload_url: "https://storage.test/private?signature=secret",
          required_headers: {
            "Content-Type": "image/png",
            "If-None-Match": "*",
          },
        },
        201,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const promise = uploadBookingFile({
      bookingId: "booking-1",
      file: new File(["payload"], "hasil.png", { type: "image/png" }),
      purpose: "deliverable",
      onProgress: vi.fn(),
      signal: controller.signal,
    });
    await vi.waitFor(() =>
      expect(FakeXMLHttpRequest.instances).toHaveLength(1),
    );

    controller.abort();

    await expect(promise).rejects.toBeInstanceOf(UploadCancelledError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("always completes once after a successful PUT despite a late abort", async () => {
    const controller = new AbortController();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response(
          {
            id: "upload-1",
            purpose: "deliverable",
            filename: "hasil.png",
            content_type: "image/png",
            size_bytes: 7,
            status: "pending",
            completed_at: null,
            expires_at: "2026-08-25T12:00:00Z",
            upload_url: "https://storage.test/private?signature=secret",
            required_headers: {
              "Content-Type": "image/png",
              "If-None-Match": "*",
            },
          },
          201,
        ),
      )
      .mockResolvedValueOnce(
        response({
          id: "upload-1",
          purpose: "deliverable",
          filename: "hasil.png",
          content_type: "image/png",
          size_bytes: 7,
          status: "completed",
          completed_at: "2026-08-25T11:00:00Z",
          expires_at: "2026-08-25T12:00:00Z",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const promise = uploadBookingFile({
      bookingId: "booking-1",
      file: new File(["payload"], "hasil.png", { type: "image/png" }),
      purpose: "deliverable",
      onProgress: vi.fn(),
      signal: controller.signal,
    });
    await vi.waitFor(() =>
      expect(FakeXMLHttpRequest.instances).toHaveLength(1),
    );

    FakeXMLHttpRequest.instances[0].succeed(200);
    controller.abort();
    const result = await promise;

    expect(result.status).toBe("completed");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[1][1] as RequestInit).signal).toBeUndefined();
  });

  it("creates an intent, PUTs directly, then completes through same-origin apiFetch", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response(
          {
            id: "upload-1",
            purpose: "deliverable",
            filename: "hasil.png",
            content_type: "image/png",
            size_bytes: 7,
            status: "pending",
            completed_at: null,
            expires_at: "2026-08-25T12:00:00Z",
            upload_url: "https://storage.test/private?signature=secret",
            required_headers: {
              "Content-Type": "image/png",
              "If-None-Match": "*",
            },
          },
          201,
        ),
      )
      .mockResolvedValueOnce(
        response({
          id: "upload-1",
          purpose: "deliverable",
          filename: "hasil.png",
          content_type: "image/png",
          size_bytes: 7,
          status: "completed",
          completed_at: "2026-08-25T11:00:00Z",
          expires_at: "2026-08-25T12:00:00Z",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["payload"], "hasil.png", { type: "image/png" });

    const promise = uploadBookingFile({
      bookingId: "booking-1",
      file,
      purpose: "deliverable",
      onProgress: vi.fn(),
      signal: new AbortController().signal,
    });
    await vi.waitFor(() =>
      expect(FakeXMLHttpRequest.instances).toHaveLength(1),
    );
    FakeXMLHttpRequest.instances[0].succeed(200);
    const result = await promise;

    expect(result.status).toBe("completed");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/bookings/booking-1/uploads",
      expect.objectContaining({ credentials: "same-origin", method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/uploads/upload-1/complete",
      expect.objectContaining({ credentials: "same-origin", method: "POST" }),
    );
  });

  it("creates a fresh intent when the user retries the workflow", async () => {
    const intents = ["upload-first", "upload-retry"];
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/uploads")) {
        const id = intents.shift();
        return response(
          {
            id,
            purpose: "deliverable",
            filename: "hasil.png",
            content_type: "image/png",
            size_bytes: 7,
            status: "pending",
            completed_at: null,
            expires_at: "2026-08-25T12:00:00Z",
            upload_url: `https://storage.test/${id}?signature=secret`,
            required_headers: {
              "Content-Type": "image/png",
              "If-None-Match": "*",
            },
          },
          201,
        );
      }
      return response({ status: "completed" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      bookingId: "booking-1",
      file: new File(["payload"], "hasil.png", { type: "image/png" }),
      purpose: "deliverable" as const,
      onProgress: vi.fn(),
      signal: new AbortController().signal,
    };

    const first = uploadBookingFile(input);
    await vi.waitFor(() =>
      expect(FakeXMLHttpRequest.instances).toHaveLength(1),
    );
    FakeXMLHttpRequest.instances[0].fail();
    await expect(first).rejects.toThrow("UPLOAD_FAILED");
    const retry = uploadBookingFile(input);
    await vi.waitFor(() =>
      expect(FakeXMLHttpRequest.instances).toHaveLength(2),
    );
    FakeXMLHttpRequest.instances[1].succeed(200);
    await retry;

    const createCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).endsWith("/uploads"),
    );
    expect(createCalls).toHaveLength(2);
    expect(FakeXMLHttpRequest.instances.map(({ url }) => url)).toEqual([
      "https://storage.test/upload-first?signature=secret",
      "https://storage.test/upload-retry?signature=secret",
    ]);
  });
});
