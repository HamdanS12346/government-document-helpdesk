import type { AttachmentStatus, AttachmentSummary } from "./api";

export type AttachmentKind = "spreadsheet" | "pdf" | "image" | "file";

export const ACCEPTED_UPLOAD_TYPES = ".png,.jpg,.jpeg,.pdf,.xlsx";
export const ATTACH_TOOLTIP = "Attach PDF, PNG, JPEG, or XLSX";
export const MAX_ATTACHMENT_COUNT = 5;
export const MAX_TOTAL_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024;
export const TOO_MANY_ATTACHMENTS_MESSAGE = `Too many attachments. Upload ${MAX_ATTACHMENT_COUNT} files or fewer.`;
export const TOTAL_UPLOAD_TOO_LARGE_MESSAGE =
  "Total upload size is too large. Upload 50 MB or less per request.";
export const ACCEPTED_UPLOAD_HINT = `Accepts PDF, PNG, JPEG, XLSX. Max ${MAX_ATTACHMENT_COUNT} files, 50 MB total.`;
export const ALL_FAILED_ATTACHMENTS_MESSAGE =
  "I received your message but couldn't process the attached files. Please check that they are valid PDF, PNG, JPEG, or XLSX files.";

export function getAttachmentKind(name: string | undefined): AttachmentKind {
  const lower = (name ?? "").toLowerCase();
  if (lower.endsWith(".xlsx")) return "spreadsheet";
  if (lower.endsWith(".pdf")) return "pdf";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg")) {
    return "image";
  }
  return "file";
}

export function buildAttachmentSummary(
  statuses: AttachmentStatus[]
): AttachmentSummary | undefined {
  if (statuses.length === 0) return undefined;

  const summary: AttachmentSummary = {
    total: statuses.length,
    images: 0,
    pdfs: 0,
    spreadsheets: 0,
    other: 0,
    succeeded: 0,
    failed: 0,
    skipped: 0,
  };

  for (const status of statuses) {
    const kind = getAttachmentKind(status.filename);
    if (kind === "image") summary.images += 1;
    else if (kind === "pdf") summary.pdfs += 1;
    else if (kind === "spreadsheet") summary.spreadsheets += 1;
    else summary.other += 1;

    if (status.status === "success") summary.succeeded += 1;
    if (status.status === "failed") summary.failed += 1;
    if (status.status === "skipped") summary.skipped += 1;
  }

  return summary;
}

export function safeStatusText(text: string | undefined, fallback: string): string {
  if (!text) return fallback;
  const unsafe = ["Traceback", 'File "', "site-packages", "RuntimeError", "Exception"];
  return unsafe.some((marker) => text.includes(marker)) ? fallback : text;
}

export function attachmentStatusLabel(status: AttachmentStatus["status"]): string {
  if (status === "success") return "Processed";
  if (status === "failed") return "Issue";
  if (status === "skipped") return "Skipped";
  return "Checked";
}

export function totalUploadSize(files: File[]): number {
  return files.reduce((total, file) => total + file.size, 0);
}

export function validateUploadLimits(files: File[]): string | null {
  if (files.length > MAX_ATTACHMENT_COUNT) {
    return TOO_MANY_ATTACHMENTS_MESSAGE;
  }
  if (totalUploadSize(files) > MAX_TOTAL_UPLOAD_SIZE_BYTES) {
    return TOTAL_UPLOAD_TOO_LARGE_MESSAGE;
  }
  return null;
}
