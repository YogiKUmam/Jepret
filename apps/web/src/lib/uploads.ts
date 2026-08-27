"use client";

import { useMutation } from "@tanstack/react-query";

import {
  apiFetch,
  type Upload,
  type UploadContentType,
  type UploadIntent,
  type UploadPurpose,
} from "./api";

export class UploadCancelledError extends Error {
  readonly code = "UPLOAD_CANCELLED";

  constructor() {
    super("UPLOAD_CANCELLED");
    this.name = "UploadCancelledError";
  }
}

export class UploadValidationError extends Error {
  readonly code = "UPLOAD_VALIDATION_FAILED";

  constructor() {
    super("UPLOAD_VALIDATION_FAILED");
    this.name = "UploadValidationError";
  }
}

const UPLOAD_LIMITS: Record<
  UploadPurpose,
  { maxSize: number; contentTypes: ReadonlySet<UploadContentType> }
> = {
  chat_attachment: {
    maxSize: 10 * 1024 * 1024,
    contentTypes: new Set([
      "image/jpeg",
      "image/png",
      "image/webp",
      "application/pdf",
    ]),
  },
  deliverable: {
    maxSize: 100 * 1024 * 1024,
    contentTypes: new Set([
      "image/jpeg",
      "image/png",
      "image/webp",
      "application/pdf",
      "application/zip",
    ]),
  },
};

function validateUploadFile(
  file: File,
  purpose: UploadPurpose,
): { filename: string; contentType: UploadContentType } {
  const limits = UPLOAD_LIMITS[purpose];
  const filename = file.name.normalize("NFKC");
  const filenameLength = Array.from(filename).length;
  const contentType = file.type as UploadContentType;
  if (
    filenameLength < 1 ||
    filenameLength > 255 ||
    filename !== filename.trim() ||
    filename.includes("/") ||
    filename.includes("\\") ||
    /\p{C}/u.test(filename) ||
    !Number.isInteger(file.size) ||
    file.size < 1 ||
    file.size > limits.maxSize ||
    !limits.contentTypes.has(contentType)
  ) {
    throw new UploadValidationError();
  }
  return { filename, contentType };
}

function uploadFailure(): Error {
  return new Error("UPLOAD_FAILED");
}

function validatedSignedHeaders(
  file: File,
  headers: Readonly<Record<string, string>>,
): Array<readonly [string, string]> {
  const allowed = new Set(["content-type", "if-none-match"]);
  const entries = Object.entries(headers);
  if (
    entries.length !== allowed.size ||
    entries.some(([name]) => !allowed.has(name.toLowerCase()))
  ) {
    throw uploadFailure();
  }
  const contentType = entries.find(
    ([name]) => name.toLowerCase() === "content-type",
  );
  const ifNoneMatch = entries.find(
    ([name]) => name.toLowerCase() === "if-none-match",
  );
  if (contentType?.[1] !== file.type || ifNoneMatch?.[1] !== "*") {
    throw uploadFailure();
  }
  return entries;
}

export function putSignedFile(
  url: string,
  file: File,
  onProgress: (percent: number) => void,
  signal: AbortSignal,
  requiredHeaders: Readonly<Record<string, string>> = {
    "Content-Type": file.type,
    "If-None-Match": "*",
  },
): Promise<void> {
  if (signal.aborted) return Promise.reject(new UploadCancelledError());

  let headers: Array<readonly [string, string]>;
  try {
    headers = validatedSignedHeaders(file, requiredHeaders);
  } catch {
    return Promise.reject(uploadFailure());
  }

  return new Promise<void>((resolve, reject) => {
    let xhr: XMLHttpRequest | null = null;
    let settled = false;
    const removeAbortListener = () =>
      signal.removeEventListener("abort", abort);
    const settle = (result: "success" | "failure" | "cancelled") => {
      if (settled) return;
      settled = true;
      removeAbortListener();
      if (xhr) {
        xhr.onload = null;
        xhr.onerror = null;
        xhr.onabort = null;
        xhr.upload.onprogress = null;
      }
      if (result === "success") resolve();
      else if (result === "cancelled") reject(new UploadCancelledError());
      else reject(uploadFailure());
    };
    const abortRequest = () => {
      try {
        xhr?.abort();
      } catch {
        // The promise has already settled with a safe application error.
      }
    };
    const abort = () => {
      if (settled) return;
      settle("cancelled");
      abortRequest();
    };
    const fail = () => {
      if (settled) return;
      settle("failure");
      abortRequest();
    };
    const reportProgress = (percent: number): boolean => {
      try {
        onProgress(percent);
        return true;
      } catch {
        fail();
        return false;
      }
    };

    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) {
      abort();
      return;
    }

    try {
      xhr = new XMLHttpRequest();
      if (signal.aborted) {
        abort();
        return;
      }
      xhr.open("PUT", url);
      xhr.withCredentials = false;
      for (const [name, value] of headers) xhr.setRequestHeader(name, value);
      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable || event.total <= 0) return;
        const percent = Math.round((event.loaded / event.total) * 100);
        reportProgress(Math.max(0, Math.min(100, percent)));
      };
      xhr.onload = () => {
        if (!xhr || xhr.status < 200 || xhr.status >= 300) {
          fail();
          return;
        }
        if (reportProgress(100)) settle("success");
      };
      xhr.onerror = fail;
      xhr.onabort = () => settle("cancelled");
      if (!reportProgress(0)) return;
      if (signal.aborted) {
        abort();
        return;
      }
      xhr.send(file);
    } catch {
      if (signal.aborted) {
        abort();
      } else {
        settle("failure");
        abortRequest();
      }
    }
  });
}

export interface UploadBookingFileInput {
  bookingId: string;
  file: File;
  purpose: UploadPurpose;
  onProgress: (percent: number) => void;
  signal: AbortSignal;
}

export async function uploadBookingFile({
  bookingId,
  file,
  purpose,
  onProgress,
  signal,
}: UploadBookingFileInput): Promise<Upload> {
  if (signal.aborted) throw new UploadCancelledError();
  const { filename, contentType } = validateUploadFile(file, purpose);
  let intent: UploadIntent;
  try {
    intent = await apiFetch<UploadIntent>(`/bookings/${bookingId}/uploads`, {
      method: "POST",
      signal,
      body: JSON.stringify({
        purpose,
        filename,
        content_type: contentType,
        size_bytes: file.size,
      }),
    });
  } catch (error) {
    if (
      signal.aborted ||
      (error instanceof DOMException && error.name === "AbortError")
    ) {
      throw new UploadCancelledError();
    }
    throw error;
  }
  await putSignedFile(
    intent.upload_url,
    file,
    onProgress,
    signal,
    intent.required_headers,
  );
  return apiFetch<Upload>(`/uploads/${intent.id}/complete`, { method: "POST" });
}

export function useUpload() {
  return useMutation({
    mutationFn: uploadBookingFile,
    retry: false,
  });
}
