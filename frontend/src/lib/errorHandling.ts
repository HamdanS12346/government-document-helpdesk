/**
 * Error classification and user messaging for the Government Helpdesk frontend.
 *
 * Categorizes failures into five distinct domains:
 * 1. authentication - expired sessions, invalid tokens, 401/403 HTTP errors
 * 2. backend        - server unreachable, connection refused, 500/503 HTTP errors
 * 3. retrieval      - vector database / ChromaDB / RAG repository errors
 * 4. upload         - encrypted PDFs, decompression bombs, corrupt files, size limit exceeded
 * 5. model          - LLM rate limits, OpenAI quota, model timeouts, classification errors
 */

import type { AttachmentStatus } from "./api.ts";

export type ErrorCategory =
  | "authentication"
  | "backend"
  | "retrieval"
  | "upload"
  | "model";

export interface ClassifiedError {
  category: ErrorCategory;
  badge: string;
  badgeIcon: string;
  title: string;
  message: string;
  suggestion: string;
}

export interface ClassifyErrorOptions {
  httpStatus?: number;
  apiStatus?: string;
  apiErrorType?: string;
  apiMessage?: string;
  attachmentStatuses?: AttachmentStatus[];
  errorObject?: unknown;
}

const CATEGORY_METADATA: Record<
  ErrorCategory,
  { badge: string; badgeIcon: string; title: string; defaultSuggestion: string }
> = {
  authentication: {
    badge: "Authentication",
    badgeIcon: "🔒",
    title: "Authentication Required",
    defaultSuggestion: "Please sign in with your email or Google account to access this service.",
  },
  backend: {
    badge: "Server Error",
    badgeIcon: "🖥️",
    title: "Helpdesk Server Unavailable",
    defaultSuggestion: "Ensure the backend server is running on port 8000 and try again.",
  },
  retrieval: {
    badge: "Document Search",
    badgeIcon: "📂",
    title: "Document Repository Error",
    defaultSuggestion: "Try rephrasing your question with specific terms, or try again in a few moments.",
  },
  upload: {
    badge: "Document Upload",
    badgeIcon: "📎",
    title: "Attachment Processing Failed",
    defaultSuggestion: "Please upload valid, unencrypted files (PDF, PNG, JPEG, XLSX) up to 50 MB total.",
  },
  model: {
    badge: "AI Service",
    badgeIcon: "⚡",
    title: "AI Model Unavailable",
    defaultSuggestion: "The AI generation service is temporarily busy or rate-limited. Please wait a moment and try again.",
  },
};

/**
 * Remove internal server traces or code stack snippets from raw error strings.
 */
function cleanErrorMessage(raw: string | undefined, fallback: string): string {
  if (!raw) return fallback;
  const unsafeMarkers = ["Traceback", 'File "', "site-packages", "RuntimeError", "Exception", "SyntaxError"];
  if (unsafeMarkers.some((m) => raw.includes(m))) {
    return fallback;
  }
  return raw.trim() || fallback;
}

/**
 * Inspects all signals (HTTP status, API status, attachment failures, error object)
 * and produces a user-friendly, categorized error report.
 */
export function classifyError(options: ClassifyErrorOptions): ClassifiedError {
  const {
    httpStatus,
    apiStatus,
    apiErrorType,
    apiMessage,
    attachmentStatuses = [],
    errorObject,
  } = options;

  // Extract combined text signals for keyword matching
  const errText = errorObject instanceof Error ? errorObject.message : String(errorObject ?? "");
  const combinedSignals = [
    apiErrorType ?? "",
    apiStatus ?? "",
    apiMessage ?? "",
    errText,
  ]
    .join(" ")
    .toLowerCase();

  // 1. Check explicit backend error_type if supplied
  if (apiErrorType === "authentication") return buildAuthError(apiMessage);
  if (apiErrorType === "upload") return buildUploadError(apiMessage, attachmentStatuses);
  if (apiErrorType === "retrieval") return buildRetrievalError(apiMessage);
  if (apiErrorType === "model") return buildModelError(apiMessage);
  if (apiErrorType === "backend") return buildBackendError(apiMessage);

  // 2. Authentication Failures (HTTP 401, 403 or auth keywords)
  if (
    httpStatus === 401 ||
    httpStatus === 403 ||
    apiStatus === "auth_error" ||
    combinedSignals.includes("unauthorized") ||
    combinedSignals.includes("forbidden") ||
    combinedSignals.includes("jwt") ||
    combinedSignals.includes("session expired") ||
    combinedSignals.includes("token expired") ||
    combinedSignals.includes("invalid token") ||
    combinedSignals.includes("access denied") ||
    combinedSignals.includes("access to this conversation thread is denied")
  ) {
    return buildAuthError(apiMessage);
  }

  // 3. Upload Failures
  const failedAttachments = attachmentStatuses.filter((s) => s.status === "failed");
  if (
    apiStatus === "input_failed" ||
    failedAttachments.length > 0 ||
    combinedSignals.includes("attachment") ||
    combinedSignals.includes("upload") ||
    combinedSignals.includes("password-protected") ||
    combinedSignals.includes("password protected") ||
    combinedSignals.includes("decompression") ||
    combinedSignals.includes("corrupt") ||
    combinedSignals.includes("unsupported format") ||
    combinedSignals.includes("too large") ||
    combinedSignals.includes("too many attachments")
  ) {
    return buildUploadError(apiMessage, attachmentStatuses);
  }

  // 4. Retrieval Failures (Vector store, ChromaDB, RAG pipeline)
  if (
    apiStatus === "retrieval_error" ||
    combinedSignals.includes("retrieval") ||
    combinedSignals.includes("chromadb") ||
    combinedSignals.includes("vector store") ||
    combinedSignals.includes("knowledge base") ||
    combinedSignals.includes("bm25") ||
    combinedSignals.includes("embedding")
  ) {
    return buildRetrievalError(apiMessage);
  }

  // 5. Model Failures (AI model timeout, rate limit, quota, 502 classification error)
  if (
    httpStatus === 502 ||
    apiStatus === "classification_error" ||
    combinedSignals.includes("classification_error") ||
    combinedSignals.includes("rate limit") ||
    combinedSignals.includes("quota exceeded") ||
    combinedSignals.includes("openai") ||
    combinedSignals.includes("model timeout") ||
    combinedSignals.includes("llm") ||
    combinedSignals.includes("context length")
  ) {
    return buildModelError(apiMessage);
  }

  // 6. Backend / Server Failures (Default fallback for network, 500, 503, system_error)
  return buildBackendError(apiMessage || errText);
}

function buildAuthError(apiMessage?: string): ClassifiedError {
  const meta = CATEGORY_METADATA.authentication;
  return {
    category: "authentication",
    badge: meta.badge,
    badgeIcon: meta.badgeIcon,
    title: meta.title,
    message: cleanErrorMessage(
      apiMessage,
      "Your session has expired or you are not authorized to perform this action."
    ),
    suggestion: meta.defaultSuggestion,
  };
}

function buildUploadError(
  apiMessage?: string,
  attachmentStatuses: AttachmentStatus[] = []
): ClassifiedError {
  const meta = CATEGORY_METADATA.upload;
  const failedList = attachmentStatuses.filter((s) => s.status === "failed");

  let detailMessage = "";
  if (failedList.length === 1 && failedList[0].error?.message) {
    detailMessage = failedList[0].error.message;
  } else if (failedList.length > 1) {
    detailMessage = `${failedList.length} files could not be processed safely.`;
  } else if (apiMessage && apiMessage !== "The input could not be processed safely.") {
    detailMessage = apiMessage;
  } else {
    detailMessage = "One or more uploaded attachments could not be processed safely.";
  }

  return {
    category: "upload",
    badge: meta.badge,
    badgeIcon: meta.badgeIcon,
    title: meta.title,
    message: cleanErrorMessage(detailMessage, "One or more uploaded attachments could not be processed safely."),
    suggestion: meta.defaultSuggestion,
  };
}

function buildRetrievalError(apiMessage?: string): ClassifiedError {
  const meta = CATEGORY_METADATA.retrieval;
  return {
    category: "retrieval",
    badge: meta.badge,
    badgeIcon: meta.badgeIcon,
    title: meta.title,
    message: cleanErrorMessage(
      apiMessage,
      "Unable to query or retrieve documents from the government document repository."
    ),
    suggestion: meta.defaultSuggestion,
  };
}

function buildModelError(apiMessage?: string): ClassifiedError {
  const meta = CATEGORY_METADATA.model;
  return {
    category: "model",
    badge: meta.badge,
    badgeIcon: meta.badgeIcon,
    title: meta.title,
    message: cleanErrorMessage(
      apiMessage,
      "The AI response generation service is currently busy, timed out, or encountered an issue."
    ),
    suggestion: meta.defaultSuggestion,
  };
}

function buildBackendError(apiMessage?: string): ClassifiedError {
  const meta = CATEGORY_METADATA.backend;
  return {
    category: "backend",
    badge: meta.badge,
    badgeIcon: meta.badgeIcon,
    title: meta.title,
    message: cleanErrorMessage(
      apiMessage,
      "The helpdesk backend service is currently unreachable or encountered an unexpected internal error."
    ),
    suggestion: meta.defaultSuggestion,
  };
}
