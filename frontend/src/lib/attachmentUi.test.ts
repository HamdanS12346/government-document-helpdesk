import assert from "node:assert/strict";
import test from "node:test";

import {
  ACCEPTED_UPLOAD_HINT,
  ACCEPTED_UPLOAD_TYPES,
  ALL_FAILED_ATTACHMENTS_MESSAGE,
  ATTACH_TOOLTIP,
  attachmentStatusLabel,
  buildAttachmentSummary,
  getAttachmentKind,
  safeStatusText,
} from "./attachmentUi.ts";

test("upload affordance copy and accept list include xlsx", () => {
  assert.equal(ACCEPTED_UPLOAD_TYPES, ".png,.jpg,.jpeg,.pdf,.xlsx");
  assert.match(ATTACH_TOOLTIP, /XLSX/);
  assert.match(ACCEPTED_UPLOAD_HINT, /XLSX/);
});

test("file chips can distinguish supported attachment kinds by extension", () => {
  assert.equal(getAttachmentKind("photo.PNG"), "image");
  assert.equal(getAttachmentKind("scan.jpeg"), "image");
  assert.equal(getAttachmentKind("notice.pdf"), "pdf");
  assert.equal(getAttachmentKind("fee-schedule.xlsx"), "spreadsheet");
  assert.equal(getAttachmentKind("legacy.xls"), "file");
});

test("attachment status labels cover success failed and skipped states", () => {
  assert.equal(attachmentStatusLabel("success"), "Processed");
  assert.equal(attachmentStatusLabel("failed"), "Issue");
  assert.equal(attachmentStatusLabel("skipped"), "Skipped");
  assert.equal(attachmentStatusLabel(undefined), "Checked");
});

test("failed status text removes unsafe backend details", () => {
  assert.equal(
    safeStatusText(
      'Traceback File "provider.py" RuntimeError raw workbook cell',
      "This attachment could not be processed safely."
    ),
    "This attachment could not be processed safely."
  );
  assert.equal(
    safeStatusText(
      "Only .xlsx spreadsheet uploads are supported.",
      "This attachment could not be processed safely."
    ),
    "Only .xlsx spreadsheet uploads are supported."
  );
});

test("all-failed fallback copy mentions every supported upload type", () => {
  assert.match(ALL_FAILED_ATTACHMENTS_MESSAGE, /PDF/);
  assert.match(ALL_FAILED_ATTACHMENTS_MESSAGE, /PNG/);
  assert.match(ALL_FAILED_ATTACHMENTS_MESSAGE, /JPEG/);
  assert.match(ALL_FAILED_ATTACHMENTS_MESSAGE, /XLSX/);
});

test("attachment summary handles xlsx-only upload responses", () => {
  assert.deepEqual(
    buildAttachmentSummary([{ filename: "benefits.xlsx", status: "success" }]),
    {
      total: 1,
      images: 0,
      pdfs: 0,
      spreadsheets: 1,
      other: 0,
      succeeded: 1,
      failed: 0,
      skipped: 0,
    }
  );
});

test("attachment summary handles mixed partial success responses", () => {
  assert.deepEqual(
    buildAttachmentSummary([
      { filename: "photo.png", status: "success" },
      {
        filename: "broken.xlsx",
        status: "failed",
        error: { message: "This spreadsheet could not be processed." },
      },
      { filename: "notice.pdf", status: "success" },
    ]),
    {
      total: 3,
      images: 1,
      pdfs: 1,
      spreadsheets: 1,
      other: 0,
      succeeded: 2,
      failed: 1,
      skipped: 0,
    }
  );
});

test("attachment summary handles all-failed and skipped responses", () => {
  assert.deepEqual(
    buildAttachmentSummary([
      { filename: "broken.xlsx", status: "failed" },
      { filename: "unsupported.gif", status: "skipped" },
    ]),
    {
      total: 2,
      images: 0,
      pdfs: 0,
      spreadsheets: 1,
      other: 1,
      succeeded: 0,
      failed: 1,
      skipped: 1,
    }
  );
});

test("empty attachment responses do not produce a visible summary", () => {
  assert.equal(buildAttachmentSummary([]), undefined);
});
