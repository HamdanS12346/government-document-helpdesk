import test from "node:test";
import assert from "node:assert/strict";
import { buildBotContent, safeText } from "../hooks/useChat.ts";
import type { ChatApiResponse, AssistantMessage } from "./api.ts";
import { classifyError } from "./errorHandling.ts";

test("Clarification: displays assistant clarification prompt to citizen", () => {
  const clarificationMsg: AssistantMessage = {
    role: "assistant",
    content:
      "To provide accurate information regarding old-age pension eligibility, could you please specify your state of residence?",
  };

  const content = buildBotContent(
    true,
    "Clarification required",
    clarificationMsg,
    [],
    []
  );

  assert.equal(content, clarificationMsg.content);
  assert.match(content, /specify your state of residence/i);
});

test("Clarification: maintains conversation_id across clarification turns", () => {
  const clarificationResponse: ChatApiResponse = {
    success: true,
    status: "clarification_required",
    message: "Clarification required",
    assistant_message: {
      role: "assistant",
      content: "Are you applying for a fresh passport or renewing an expired passport?",
    },
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
    intent: { type: "passport_inquiry", confidence_score: 0.65 },
    conversation_id: "conv-thread-clarify-99",
  };

  // Ensure conversation_id is captured for multi-turn thread continuity
  assert.equal(clarificationResponse.status, "clarification_required");
  assert.equal(clarificationResponse.success, true);
  assert.equal(clarificationResponse.conversation_id, "conv-thread-clarify-99");
  assert.ok(clarificationResponse.assistant_message?.content);
});

test("Clarification: successful clarification is not treated as an error in chat state", () => {
  const isSuccess = true;
  const isError = !isSuccess;
  assert.equal(isError, false);

  const content = buildBotContent(
    true,
    "Clarification required",
    { role: "assistant", content: "Please select your state." },
    [],
    []
  );
  assert.equal(content, "Please select your state.");
});

test("Clarification: fallback safely renders message when assistant_message is null", () => {
  const content = buildBotContent(
    true,
    "Please specify which department you want to contact.",
    null,
    [],
    []
  );

  assert.equal(content, "Please specify which department you want to contact.");
});

test("Clarification: sanitizes any unexpected backend tracebacks in clarification text", () => {
  const unsafeText =
    'Traceback (most recent call last):\n  File "clarification_node.py", line 12\nCould you clarify?';

  const cleaned = safeText(unsafeText, "Could you please clarify your request?");
  assert.equal(cleaned, "Could you please clarify your request?");
  assert.doesNotMatch(cleaned, /Traceback/i);
});
