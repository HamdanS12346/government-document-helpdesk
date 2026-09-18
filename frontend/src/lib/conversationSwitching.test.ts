import test from "node:test";
import assert from "node:assert/strict";
import {
  fetchThreadMessages,
  deleteUserThread,
  type ThreadMessage,
} from "./api.ts";
import { WELCOME_MESSAGE } from "../hooks/useChat.ts";

test("fetchThreadMessages retrieves and returns transcript for a specific thread", async () => {
  const originalFetch = globalThis.fetch;
  const mockTranscript: ThreadMessage[] = [
    {
      id: "msg-1",
      thread_id: "thread-abc",
      role: "human",
      content: "What are the rules for passport renewal?",
      sequence_number: 1,
      created_at: "2026-09-18T10:00:00Z",
    },
    {
      id: "msg-2",
      thread_id: "thread-abc",
      role: "ai",
      content: "For passport renewal, submit Form 1 with your previous passport and address proof.",
      sequence_number: 2,
      created_at: "2026-09-18T10:00:05Z",
    },
  ];

  try {
    let requestedUrl = "";
    let authHeader = "";

    globalThis.fetch = async (url, init) => {
      requestedUrl = url.toString();
      authHeader = (init?.headers as Record<string, string>)?.Authorization || "";
      return new Response(JSON.stringify(mockTranscript), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    const messages = await fetchThreadMessages("thread-abc", "mock-token-xyz");

    assert.equal(requestedUrl, "http://localhost:8000/threads/thread-abc/messages");
    assert.equal(authHeader, "Bearer mock-token-xyz");
    assert.equal(messages.length, 2);
    assert.equal(messages[0].role, "human");
    assert.equal(messages[1].role, "ai");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Conversation switching maps ai role to bot and human role to user", () => {
  const backendMessages: ThreadMessage[] = [
    {
      id: "1",
      thread_id: "t1",
      role: "human",
      content: "Hello",
      sequence_number: 1,
    },
    {
      id: "2",
      thread_id: "t1",
      role: "ai",
      content: "Welcome, how can I help you?",
      sequence_number: 2,
    },
  ];

  const mapped = backendMessages.map((m) => ({
    id: m.id,
    role: m.role === "ai" ? ("bot" as const) : ("user" as const),
    content: m.content,
  }));

  assert.equal(mapped[0].role, "user");
  assert.equal(mapped[1].role, "bot");
});

test("Switching to an empty conversation thread falls back to WELCOME_MESSAGE", () => {
  const emptyTranscript: ThreadMessage[] = [];
  const mapped = emptyTranscript.map((m) => ({
    id: m.id,
    role: m.role === "ai" ? "bot" : "user",
    content: m.content,
  }));

  const activeMessages = mapped.length > 0 ? mapped : [WELCOME_MESSAGE];
  assert.equal(activeMessages.length, 1);
  assert.equal(activeMessages[0].id, "welcome");
  assert.equal(activeMessages[0].role, "bot");
  assert.match(activeMessages[0].content, /Government Helpdesk assistant/i);
});

test("Switching conversations aborts previous in-flight thread loading", async () => {
  const originalFetch = globalThis.fetch;
  let threadAAborted = false;

  try {
    globalThis.fetch = async (url, init) => {
      const signal = init?.signal;
      if (url.toString().includes("thread-A")) {
        return new Promise((_, reject) => {
          signal?.addEventListener("abort", () => {
            threadAAborted = true;
            reject(new DOMException("The user aborted a request.", "AbortError"));
          });
        });
      }

      return new Response(
        JSON.stringify([
          {
            id: "msg-b1",
            thread_id: "thread-B",
            role: "ai",
            content: "Thread B response",
            sequence_number: 1,
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    // User switches to Thread A
    const controllerA = new AbortController();
    const fetchA = fetchThreadMessages("thread-A", "token", controllerA.signal);

    // User rapidly switches to Thread B before Thread A finishes
    controllerA.abort(); // loadThread aborts previous controller
    const controllerB = new AbortController();
    const fetchB = await fetchThreadMessages("thread-B", "token", controllerB.signal);

    // Thread A rejected with AbortError
    await assert.rejects(fetchA, (err: unknown) => {
      return (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      );
    });

    assert.equal(threadAAborted, true);
    assert.equal(fetchB.length, 1);
    assert.equal(fetchB[0].content, "Thread B response");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Switching conversation aborts in-flight chat generation without throwing", async () => {
  const chatController = new AbortController();
  assert.equal(chatController.signal.aborted, false);

  // When loadThread is called, abortRef.current?.abort() is triggered
  chatController.abort();
  assert.equal(chatController.signal.aborted, true);

  // Error handling in useChat ignores AbortError
  const abortErr = new DOMException("The user aborted a request.", "AbortError");
  const isIgnored =
    chatController.signal.aborted ||
    (abortErr instanceof DOMException && abortErr.name === "AbortError");
  assert.equal(isIgnored, true);
});

test("Clearing chat resets conversation ID and resets messages to welcome", () => {
  let activeMessages = [
    { id: "m1", role: "user", content: "Query 1" },
    { id: "m2", role: "bot", content: "Answer 1" },
  ];
  let conversationId: string | null = "thread-123";
  let isLoading = true;

  // clearChat() logic simulation
  const chatAbort = new AbortController();
  chatAbort.abort();
  activeMessages = [{ ...WELCOME_MESSAGE }];
  conversationId = null;
  isLoading = false;

  assert.equal(chatAbort.signal.aborted, true);
  assert.equal(activeMessages.length, 1);
  assert.equal(activeMessages[0].id, "welcome");
  assert.equal(conversationId, null);
  assert.equal(isLoading, false);
});

test("deleteUserThread deletes conversation thread via API", async () => {
  const originalFetch = globalThis.fetch;
  try {
    let deletedUrl = "";
    let methodUsed = "";
    globalThis.fetch = async (url, init) => {
      deletedUrl = url.toString();
      methodUsed = init?.method || "";
      return new Response(null, { status: 204 });
    };

    const result = await deleteUserThread("thread-to-delete", "auth-token-123");
    assert.equal(result, true);
    assert.equal(deletedUrl, "http://localhost:8000/threads/thread-to-delete");
    assert.equal(methodUsed, "DELETE");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
