"use client";

import { useRef, useState } from "react";

import type { Upload, UploadPurpose } from "@/lib/api";
import {
  UploadCancelledError,
  UploadValidationError,
  uploadBookingFile,
} from "@/lib/uploads";

export interface UploadFieldProps {
  bookingId: string;
  purpose: UploadPurpose;
  onUploaded: (upload: Upload) => void;
  disabled?: boolean;
  label?: string;
  accept?: string;
}

export function UploadField({
  bookingId,
  purpose,
  onUploaded,
  disabled = false,
  label = "Pilih berkas",
  accept,
}: UploadFieldProps) {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [status, setStatus] = useState<"idle" | "uploading" | "error" | "success">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const maxMb = purpose === "chat_attachment" ? 10 : 100;
  const defaultAccept =
    purpose === "chat_attachment"
      ? "image/jpeg,image/png,image/webp,application/pdf"
      : "image/jpeg,image/png,image/webp,application/pdf,application/zip";

  const handleStartUpload = async (selectedFile: File) => {
    setFile(selectedFile);
    setProgress(0);
    setStatus("uploading");
    setErrorMessage(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const uploaded = await uploadBookingFile({
        bookingId,
        file: selectedFile,
        purpose,
        onProgress: (p) => setProgress(p),
        signal: controller.signal,
      });

      setStatus("success");
      onUploaded(uploaded);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (error) {
      if (error instanceof UploadCancelledError) {
        setStatus("idle");
        setFile(null);
        setProgress(0);
        return;
      }

      setStatus("error");
      if (error instanceof UploadValidationError) {
        setErrorMessage(
          `Berkas tidak valid atau melebihi batas ukuran (${maxMb}MB). Format yang didukung: JPG, PNG, WEBP, PDF${
            purpose === "deliverable" ? ", ZIP" : ""
          }.`,
        );
      } else {
        setErrorMessage("Pengunggahan berkas gagal. Silakan coba lagi.");
      }
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    void handleStartUpload(selected);
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleRetry = () => {
    if (file) {
      void handleStartUpload(file);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <label className="relative inline-flex min-h-11 cursor-pointer items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 text-sm font-medium text-[var(--surface-foreground)] transition hover:bg-[var(--border)] active:scale-[0.98]">
          <span>{status === "uploading" ? "Mengunggah…" : label}</span>
          <input
            ref={fileInputRef}
            type="file"
            accept={accept ?? defaultAccept}
            disabled={disabled || status === "uploading"}
            onChange={handleFileChange}
            className="sr-only"
          />
        </label>

        {status === "uploading" ? (
          <button
            type="button"
            onClick={handleCancel}
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-red-500/30 px-3 text-xs font-medium text-red-500 transition hover:bg-red-500/10 active:scale-[0.98]"
          >
            Batal
          </button>
        ) : null}

        {status === "error" && file ? (
          <button
            type="button"
            onClick={handleRetry}
            className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-4 text-sm font-medium text-[var(--primary-foreground)] transition active:scale-[0.98]"
          >
            Coba lagi
          </button>
        ) : null}
      </div>

      {status === "uploading" ? (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-[var(--muted)]">
            <span className="truncate">{file?.name}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
            <div
              className="h-full bg-[var(--primary)] transition-all duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      ) : null}

      {status === "error" && errorMessage ? (
        <p role="alert" className="text-xs text-red-500">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
