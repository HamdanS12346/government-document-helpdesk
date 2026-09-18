import test from "node:test";
import assert from "node:assert/strict";
import { postChat, fetchThreadMessages } from "./api.ts";

test("postChat respects AbortSignal and propagates abort error", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, init) => {
      const signal = init?.signal;
      return new Promise((_, reject) => {
        if (signal?.aborted) {
          return reject(new DOMException("The operation was aborted", "AbortError"));
        }
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted", "AbortError"));
        });
      });
    };

    const controller = new AbortController();
    const promise = postChat("Hello", [], null, null, controller.signal);
    controller.abort();

    await assert.rejects(promise, (err: unknown) => {
      return (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      );
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetchThreadMessages respects AbortSignal and propagates abort error", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, init) => {
      const signal = init?.signal;
      return new Promise((_, reject) => {
        if (signal?.aborted) {
          return reject(new DOMException("The operation was aborted", "AbortError"));
        }
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted", "AbortError"));
        });
      });
    };

    const controller = new AbortController();
    const promise = fetchThreadMessages("thread-123", "dummy-token", controller.signal);
    controller.abort();

    await assert.rejects(promise, (err: unknown) => {
      return (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      );
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("postChat completes normally when not aborted", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => {
      return new Response(
        JSON.stringify({
          success: true,
          status: "completed",
          message: "Success",
          assistant_message: { role: "assistant", content: "Hello world" },
          attachment_statuses: [],
          attachment_summary: {
            total: 0,
            images: 0,
            pdfs: 0,
            spreadsheets: 0,
            other: 0,
            succeeded: 0,
            failed: 0,
            skipped: 0,
          },
          warnings: [],
          normalized_input: {},
          intent: null,
          conversation_id: "conv-1",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    };

    const controller = new AbortController();
    const res = await postChat("Hello", [], null, null, controller.signal);
    assert.equal(res.success, true);
    assert.equal(res.assistant_message?.content, "Hello world");
    assert.equal(res.httpStatus, 200);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
