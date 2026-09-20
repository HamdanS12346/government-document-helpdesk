import test from "node:test";
import assert from "node:assert/strict";
import { postChat } from "./api.ts";
import { classifyError } from "./errorHandling.ts";
import { safeText } from "../hooks/useChat.ts";

test("API failure: handles network disconnect or server offline", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => {
      throw new TypeError("fetch failed");
    };

    let caughtError: unknown;
    try {
      await postChat("Check status", []);
    } catch (err) {
      caughtError = err;
    }

    assert.ok(caughtError instanceof TypeError);
    const classified = classifyError({ errorObject: caughtError });
    assert.equal(classified.category, "backend");
    assert.equal(classified.badge, "Server Error");
    assert.equal(classified.badgeIcon, "🖥️");
    assert.match(classified.suggestion, /backend server/i);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API failure: handles HTTP 401 Unauthorized by classifying as authentication error", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => {
      return new Response(
        JSON.stringify({
          detail: "Could not validate credentials",
        }),
        {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }
      );
    };

    const response = await postChat("Private thread query", [], "thread-secret", "expired-token");

    assert.equal(response.success, false);
    assert.equal(response.httpStatus, 401);

    const classified = classifyError({
      httpStatus: response.httpStatus,
      apiMessage: (response as any).detail,
    });

    assert.equal(classified.category, "authentication");
    assert.equal(classified.badge, "Authentication");
    assert.equal(classified.badgeIcon, "🔒");
    assert.match(classified.suggestion, /sign in/i);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API failure: handles HTTP 500 Internal Server Error gracefully", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => {
      return new Response(
        JSON.stringify({
          success: false,
          status: "system_error",
          message: "Internal server error in workflow execution",
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    };

    const response = await postChat("Trigger crash", []);

    assert.equal(response.success, false);
    assert.equal(response.httpStatus, 500);

    const classified = classifyError({
      httpStatus: response.httpStatus,
      apiStatus: response.status,
      apiMessage: response.message,
    });

    assert.equal(classified.category, "backend");
    assert.equal(classified.badge, "Server Error");
    assert.match(classified.message, /workflow execution/i);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API failure: handles model and classification errors as AI service issues", async () => {
  const classified502 = classifyError({ httpStatus: 502 });
  assert.equal(classified502.category, "model");
  assert.equal(classified502.badge, "AI Service");
  assert.equal(classified502.badgeIcon, "⚡");
  assert.match(classified502.suggestion, /busy|rate-limited|try again/i);

  const classifiedClassificationError = classifyError({
    apiStatus: "classification_error",
    apiMessage: "Intent classification model timed out",
  });
  assert.equal(classifiedClassificationError.category, "model");
  assert.equal(classifiedClassificationError.title, "AI Model Unavailable");
});

test("API failure: sanitizes raw server tracebacks from user-facing error messages", () => {
  const rawBackendTraceback =
    'Traceback (most recent call last):\n  File "/usr/local/lib/python3.11/site-packages/langchain/chains.py", line 100\nRuntimeError: Database lock acquired';

  const sanitized = safeText(
    rawBackendTraceback,
    "The server encountered an error while processing your request. Please try again."
  );

  assert.equal(
    sanitized,
    "The server encountered an error while processing your request. Please try again."
  );
  assert.doesNotMatch(sanitized, /Traceback/i);
  assert.doesNotMatch(sanitized, /site-packages/i);
  assert.doesNotMatch(sanitized, /RuntimeError/i);
});

test("API failure: non-200 responses with non-JSON bodies fall back gracefully", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => {
      return new Response("Bad Gateway HTML page", { status: 502 });
    };

    const response = await postChat("Hello", []);
    assert.equal(response.success, false);
    assert.equal(response.httpStatus, 502);

    const classified = classifyError({ httpStatus: response.httpStatus });
    assert.equal(classified.category, "model");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
