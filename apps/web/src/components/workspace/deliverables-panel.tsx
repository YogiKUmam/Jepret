"use client";

import { useState } from "react";

import type { BookingStatus, Deliverable, Upload } from "@/lib/api";
import {
  requestPrivateDownload,
  useCreateDeliverable,
  useDeleteDeliverable,
} from "@/lib/deliverables";
import { UploadField } from "./upload-field";

function formatBytes(bytes: number | null) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface DeliverablesPanelProps {
  bookingId: string;
  role: "client" | "creator";
  status: BookingStatus;
  deliverables: Deliverable[];
}

export function DeliverablesPanel({
  bookingId,
  role,
  status,
  deliverables,
}: DeliverablesPanelProps) {
  const createDeliverable = useCreateDeliverable(bookingId);
  const deleteDeliverable = useDeleteDeliverable(bookingId);

  const [addMode, setAddMode] = useState<"file" | "link">("file");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [externalUrl, setExternalUrl] = useState("");
  const [uploadedFile, setUploadedFile] = useState<Upload | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const canEdit = role === "creator" && status === "in_progress";

  const handleDownload = async (uploadId: string) => {
    setDownloadingId(uploadId);
    try {
      const { url } = await requestPrivateDownload(uploadId);
      if (typeof window !== "undefined") {
        window.open(url, "_blank", "noopener,noreferrer");
      }
    } catch {
      // ignore
    } finally {
      setDownloadingId(null);
    }
  };

  const handleCreateFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setFormError("Judul hasil pemotretan wajib diisi.");
      return;
    }
    if (!uploadedFile) {
      setFormError("Silakan unggah berkas terlebih dahulu.");
      return;
    }

    setFormError(null);
    try {
      await createDeliverable.mutateAsync({
        source_type: "private_file",
        title: title.trim(),
        description: description.trim() || null,
        upload_id: uploadedFile.id,
      });
      setTitle("");
      setDescription("");
      setUploadedFile(null);
    } catch {
      setFormError("Gagal menambahkan hasil. Silakan coba lagi.");
    }
  };

  const handleCreateLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setFormError("Judul tautan wajib diisi.");
      return;
    }
    if (!externalUrl.trim()) {
      setFormError("URL tautan wajib diisi.");
      return;
    }

    try {
      new URL(externalUrl.trim());
    } catch {
      setFormError("Format tautan URL tidak valid.");
      return;
    }

    setFormError(null);
    try {
      await createDeliverable.mutateAsync({
        source_type: "external_link",
        title: title.trim(),
        description: description.trim() || null,
        external_url: externalUrl.trim(),
      });
      setTitle("");
      setDescription("");
      setExternalUrl("");
    } catch {
      setFormError("Gagal menambahkan tautan hasil. Silakan coba lagi.");
    }
  };

  return (
    <div className="space-y-6 rounded-3xl border border-[var(--border)] bg-[var(--background)] p-4 text-[var(--foreground)] sm:p-6">
      <div>
        <h2 className="text-xl font-bold">Hasil Pemotretan & Berkas</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          {role === "creator"
            ? "Unggah foto/video resolusi tinggi atau cantumkan tautan cloud drive (Google Drive / Dropbox) untuk diserahkan ke klien."
            : "Kumpulan hasil foto dan rekaman video yang diserahkan oleh kreator untuk Anda."}
        </p>
      </div>

      {/* Deliverables List */}
      <div className="space-y-3">
        {deliverables.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
            {role === "creator"
              ? "Belum ada berkas hasil yang diunggah. Tambahkan berkas foto/video atau tautan drive di bawah."
              : "Kreator belum mengunggah hasil pekerjaan."}
          </div>
        ) : (
          <ul className="list-none space-y-3 p-0 m-0">
            {deliverables.map((item) => {
              const isFile = item.source_type === "private_file";
              return (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-[var(--border)] px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
                        {isFile ? "Berkas" : "Tautan"}
                      </span>
                      <h3 className="font-semibold">{item.title}</h3>
                    </div>
                    {item.description ? (
                      <p className="text-xs text-[var(--muted)]">
                        {item.description}
                      </p>
                    ) : null}
                    <div className="text-xs text-[var(--muted)]">
                      {isFile ? (
                        <span>
                          {item.filename} · {formatBytes(item.size_bytes)}
                        </span>
                      ) : (
                        <a
                          href={item.external_url ?? "#"}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-[var(--primary)] underline underline-offset-2"
                        >
                          {item.external_host || item.external_url}
                        </a>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isFile && item.upload_id ? (
                      <button
                        type="button"
                        onClick={() => handleDownload(item.upload_id!)}
                        disabled={downloadingId === item.upload_id}
                        className="inline-flex min-h-10 items-center justify-center rounded-xl bg-[var(--primary)] px-4 text-xs font-medium text-[var(--primary-foreground)] transition active:scale-[0.98] disabled:opacity-60"
                      >
                        {downloadingId === item.upload_id
                          ? "Memuat…"
                          : "Unduh berkas"}
                      </button>
                    ) : !isFile && item.external_url ? (
                      <a
                        href={item.external_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex min-h-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--background)] px-4 text-xs font-medium transition hover:bg-[var(--border)] active:scale-[0.98]"
                      >
                        Buka tautan
                      </a>
                    ) : null}

                    {canEdit ? (
                      <button
                        type="button"
                        onClick={() => deleteDeliverable.mutate(item.id)}
                        disabled={deleteDeliverable.isPending}
                        className="inline-flex min-h-10 items-center justify-center rounded-xl border border-red-500/30 px-3 text-xs font-medium text-red-500 transition hover:bg-red-500/10 active:scale-[0.98] disabled:opacity-50"
                      >
                        Hapus
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Creator Form to Add Deliverable */}
      {canEdit ? (
        <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <h3 className="font-semibold">Tambah Hasil Pekerjaan</h3>

          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => {
                setAddMode("file");
                setFormError(null);
              }}
              className={`min-h-10 rounded-xl px-4 text-xs font-medium transition ${
                addMode === "file"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "border border-[var(--border)] text-[var(--foreground)]"
              }`}
            >
              Unggah Berkas (Maks. 100MB)
            </button>
            <button
              type="button"
              onClick={() => {
                setAddMode("link");
                setFormError(null);
              }}
              className={`min-h-10 rounded-xl px-4 text-xs font-medium transition ${
                addMode === "link"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "border border-[var(--border)] text-[var(--foreground)]"
              }`}
            >
              Tautan Google Drive / Dropbox
            </button>
          </div>

          {formError ? (
            <p role="alert" className="mt-3 text-xs text-red-500">
              {formError}
            </p>
          ) : null}

          {addMode === "file" ? (
            <form onSubmit={handleCreateFile} className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-medium text-[var(--muted)]">
                  Judul Berkas
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Contoh: Foto Edit Pilihan (High-Res)"
                  required
                  className="mt-1 min-h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--muted)]">
                  Keterangan (Opsional)
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Contoh: Format JPG resolusi penuh untuk cetak"
                  className="mt-1 min-h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                />
              </div>

              <div className="pt-1">
                <UploadField
                  bookingId={bookingId}
                  purpose="deliverable"
                  label={
                    uploadedFile
                      ? `Berkas terpilih: ${uploadedFile.filename}`
                      : "Pilih berkas foto/ZIP"
                  }
                  onUploaded={(upload) => {
                    setUploadedFile(upload);
                    setFormError(null);
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={
                  !uploadedFile || !title.trim() || createDeliverable.isPending
                }
                className="mt-2 inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {createDeliverable.isPending
                  ? "Menyimpan…"
                  : "Simpan Berkas Hasil"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleCreateLink} className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-medium text-[var(--muted)]">
                  Judul Tautan
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Contoh: Folder Full Video & Raw Footage"
                  required
                  className="mt-1 min-h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--muted)]">
                  URL Tautan Cloud Drive
                </label>
                <input
                  type="url"
                  value={externalUrl}
                  onChange={(e) => setExternalUrl(e.target.value)}
                  placeholder="https://drive.google.com/drive/folders/..."
                  required
                  className="mt-1 min-h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--muted)]">
                  Keterangan (Opsional)
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Contoh: Akses terbuka untuk klien"
                  className="mt-1 min-h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                />
              </div>

              <button
                type="submit"
                disabled={
                  !externalUrl.trim() ||
                  !title.trim() ||
                  createDeliverable.isPending
                }
                className="mt-2 inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {createDeliverable.isPending
                  ? "Menyimpan…"
                  : "Simpan Tautan Hasil"}
              </button>
            </form>
          )}
        </div>
      ) : null}
    </div>
  );
}
