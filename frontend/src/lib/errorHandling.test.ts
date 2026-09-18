import test from "node:test";
import assert from "node:assert/strict";
import { classifyError } from "./errorHandling.ts";

test("classifyError detects authentication failures from HTTP 401/403 status", () => {
  const err401 = classifyError({ httpStatus: 401 });
  assert.equal(err401.category, "authentication");
  assert.equal(err401.title, "Authentication Required");
  assert.match(err401.suggestion, /sign in/i);

  const err403 = classifyError({
    httpStatus: 403,
    apiMessage: "Access to this conversation thread is denied.",
  });
  assert.equal(err403.category, "authentication");
  assert.match(err403.message, /Access to this conversation thread is denied/i);
});

test("classifyError detects authentication failures from token and session keywords", () => {
  const errToken = classifyError({
    errorObject: new Error("JWT token expired"),
  });
  assert.equal(errToken.category, "authentication");

  const errAuth = classifyError({
    apiStatus: "auth_error",
    apiMessage: "User session expired",
  });
  assert.equal(errAuth.category, "authentication");
});

test("classifyError detects upload failures from input_failed and failed attachments", () => {
  const errUpload = classifyError({
    apiStatus: "input_failed",
    attachmentStatuses: [
      {
        filename: "salary_slip.pdf",
        status: "failed",
        error: { message: "The PDF is encrypted or password-protected." },
      },
    ],
  });
  assert.equal(errUpload.category, "upload");
  assert.equal(errUpload.title, "Attachment Processing Failed");
  assert.match(errUpload.message, /password-protected/i);
  assert.match(errUpload.suggestion, /PDF, PNG, JPEG, XLSX/i);
});

test("classifyError detects upload failures from file size and count limit errors", () => {
  const errLimit = classifyError({
    apiMessage: "Total upload size is too large. Upload 50 MB or less per request.",
  });
  assert.equal(errLimit.category, "upload");
  assert.match(errLimit.message, /50 MB/i);
});

test("classifyError detects retrieval failures from ChromaDB and vector store signals", () => {
  const errRetrieval = classifyError({
    apiStatus: "retrieval_error",
    apiMessage: "Failed to connect to ChromaDB vector store.",
  });
  assert.equal(errRetrieval.category, "retrieval");
  assert.equal(errRetrieval.title, "Document Repository Error");
  assert.match(errRetrieval.suggestion, /rephrasing your question/i);

  const errRAG = classifyError({
    errorObject: new Error("Knowledge base embedding retrieval failed"),
  });
  assert.equal(errRAG.category, "retrieval");
});

test("classifyError detects model failures from classification_error and HTTP 502", () => {
  const err502 = classifyError({
    httpStatus: 502,
    apiStatus: "classification_error",
    apiMessage: "The request could not be classified right now. Please try again.",
  });
  assert.equal(err502.category, "model");
  assert.equal(err502.title, "AI Model Unavailable");
  assert.match(err502.suggestion, /wait a moment/i);

  const errQuota = classifyError({
    apiMessage: "OpenAI rate limit reached. Quota exceeded.",
  });
  assert.equal(errQuota.category, "model");
});

test("classifyError detects backend failures from network errors, 500, and 503", () => {
  const errNetwork = classifyError({
    errorObject: new TypeError("Failed to fetch"),
  });
  assert.equal(errNetwork.category, "backend");
  assert.equal(errNetwork.title, "Helpdesk Server Unavailable");
  assert.match(errNetwork.suggestion, /port 8000/i);

  const err500 = classifyError({
    httpStatus: 500,
    apiStatus: "system_error",
  });
  assert.equal(err500.category, "backend");

  const err503 = classifyError({
    httpStatus: 503,
  });
  assert.equal(err503.category, "backend");
});

test("classifyError sanitizes internal python tracebacks from error messages", () => {
  const errTraceback = classifyError({
    httpStatus: 500,
    apiMessage: 'Traceback (most recent call last):\n  File "server.py", line 42, in process\nRuntimeError: DB fail',
  });
  assert.equal(errTraceback.category, "backend");
  // Should not leak raw python traceback to user
  assert.doesNotMatch(errTraceback.message, /Traceback/);
  assert.doesNotMatch(errTraceback.message, /server\.py/);
});

test("classifyError respects explicit apiErrorType override", () => {
  const errExplicit = classifyError({
    apiErrorType: "retrieval",
    httpStatus: 500,
  });
  assert.equal(errExplicit.category, "retrieval");
});
