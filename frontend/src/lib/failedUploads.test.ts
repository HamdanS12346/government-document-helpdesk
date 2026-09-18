import test from "node:test";
import assert from "node:assert/strict";
import {
  validateUploadLimits,
  safeStatusText,
  TOO_MANY_ATTACHMENTS_MESSAGE,
  TOTAL_UPLOAD_TOO_LARGE_MESSAGE,
  ALL_FAILED_ATTACHMENTS_MESSAGE,
} from "./attachmentUi.ts";
import { classifyError } from "./errorHandling.ts";
import { buildBotContent } from "../hooks/useChat.ts";
import type { AttachmentStatus, AssistantMessage } from "./api.ts";

test("Failed uploads: file count limit validation rejects more than 5 files", () => {
  const files = [
    { name: "f1.pdf", size: 1000 },
    { name: "f2.pdf", size: 1000 },
    { name: "f3.pdf", size: 1000 },
    { name: "f4.pdf", size: 1000 },
    { name: "f5.pdf", size: 1000 },
    { name: "f6.pdf", size: 1000 },
  ] as File[];

  const error = validateUploadLimits(files);
  assert.equal(error, TOO_MANY_ATTACHMENTS_MESSAGE);
});

test("Failed uploads: total size validation rejects payload over 50 MB", () => {
  const files = [
    { name: "huge.pdf", size: 52 * 1024 * 1024 },
  ] as File[];

  const error = validateUploadLimits(files);
  assert.equal(error, TOTAL_UPLOAD_TOO_LARGE_MESSAGE);
});

test("Failed uploads: accepts uploads within count and size limits", () => {
  const files = [
    { name: "doc1.pdf", size: 10 * 1024 * 1024 },
    { name: "doc2.xlsx", size: 5 * 1024 * 1024 },
  ] as File[];

  const error = validateUploadLimits(files);
  assert.equal(error, null);
});

test("Failed uploads: all-failed attachments triggers ALL_FAILED_ATTACHMENTS_MESSAGE", () => {
  const statuses: AttachmentStatus[] = [
    {
      filename: "protected_aadhaar.pdf",
      status: "failed",
      error: { message: "The PDF is encrypted or password-protected." },
    },
    {
      filename: "corrupt_data.xlsx",
      status: "failed",
      error: { message: "Failed to parse spreadsheet content." },
    },
  ];

  const content = buildBotContent(true, "Files received", null, [], statuses);

  assert.equal(content, ALL_FAILED_ATTACHMENTS_MESSAGE);
  assert.match(content, /PDF/i);
  assert.match(content, /XLSX/i);
  assert.match(content, /PNG/i);
});

test("Failed uploads: partial upload failure preserves assistant answer", () => {
  const statuses: AttachmentStatus[] = [
    {
      filename: "valid_passport.pdf",
      status: "success",
    },
    {
      filename: "corrupt_doc.pdf",
      status: "failed",
      error: { message: "Corrupted PDF header" },
    },
  ];

  const assistantMessage: AssistantMessage = {
    role: "assistant",
    content: "I processed your passport application from the first document.",
  };

  const content = buildBotContent(true, "Completed", assistantMessage, [], statuses);
  assert.equal(content, "I processed your passport application from the first document.");
});

test("Failed uploads: safeStatusText sanitizes internal backend tracebacks", () => {
  const unsafeBackendError =
    'Traceback (most recent call last):\n  File "pdf_processor.py", line 42, in process_pdf\nValueError: Invalid xref stream';

  const label = safeStatusText(unsafeBackendError, "Could not be processed");
  assert.equal(label, "Could not be processed");
  assert.doesNotMatch(label, /Traceback/i);
  assert.doesNotMatch(label, /pdf_processor\.py/i);
});

test("Failed uploads: classifyError categorizes attachment failures as upload domain", () => {
  const classified = classifyError({
    apiStatus: "input_failed",
    attachmentStatuses: [
      {
        filename: "ration_card.pdf",
        status: "failed",
        error: { message: "The PDF is encrypted or password-protected." },
      },
    ],
  });

  assert.equal(classified.category, "upload");
  assert.equal(classified.badge, "Document Upload");
  assert.equal(classified.badgeIcon, "📎");
  assert.equal(classified.title, "Attachment Processing Failed");
  assert.match(classified.message, /encrypted or password-protected/i);
  assert.match(classified.suggestion, /unencrypted/i);
});
