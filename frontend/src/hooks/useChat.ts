"use client";

import { useCallback, useRef, useState } from "react";
import {
  postChat,
  fetchThreadMessages,
  type AttachmentStatus,
  type ChatApiResponse,
  type ProcessingWarning,
  type AssistantMessage,
} from "@/lib/api";

export type MessageRole = "user" | "bot";

export type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  /** Names of files attached to this message (user messages only) */
  attachmentNames?: string[];
  /** Per-file processing results (bot messages only) */
  attachmentStatuses?: AttachmentStatus[];
  /** Non-fatal processing warnings */
  warnings?: string[];
  /** True when the API returned success: false */
  isError?: boolean;
  /** True while the assistant response is actively streaming */
  isStreaming?: boolean;
};

type UseChatReturn = {
  messages: ChatMessage[];
  isLoading: boolean;
  pendingQuery: string;
  conversationId: string | null;
  sendMessage: (text: string, files: File[], token?: string | null) => Promise<void>;
  loadThread: (threadId: string, token: string) => Promise<void>;
  clearChat: () => void;
  setPendingQuery: (q: string) => void;
};

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "bot",
  content:
    "Hello! I'm your Government Helpdesk assistant. I can help you with information about government documents, procedures, eligibility, fees and more.\n\nWhat would you like to know today?",
  timestamp: new Date(),
};

function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

function safeText(text: string | undefined, fallback: string): string {
  if (!text) return fallback;
  const unsafe = ["Traceback", 'File "', "site-packages", "RuntimeError", "Exception"];
  return unsafe.some((p) => text.includes(p)) ? fallback : text;
}

function buildBotContent(
  success: boolean,
  message: string,
  assistantMessage: AssistantMessage | null,
  warnings: ProcessingWarning[],
  attachmentStatuses: AttachmentStatus[]
): string {
  // --- Priority 1: use the real LLM response when present ---
  if (assistantMessage?.content) {
    return safeText(assistantMessage.content, "Sorry, I couldn't generate a response. Please try again.");
  }

  // --- Priority 2: input processing failure ---
  if (!success) {
    return safeText(message, "Sorry, I couldn't process that request. Please try again.");
  }

  // --- Priority 3: all attachments failed ---
  const failedFiles = attachmentStatuses.filter((s) => s.status === "failed");
  if (failedFiles.length > 0 && attachmentStatuses.every((s) => s.status === "failed")) {
    return "I received your message but couldn't process the attached files. Please check that they are valid PDF, PNG, or JPEG files.";
  }

  // --- Priority 4: generic status fallback (should not normally be seen) ---
  return safeText(message, "Your message was received. Please try asking again.");
}

/** Stream response text progressively token-by-token into state */
async function streamBotResponse(
  botMsgId: string,
  fullText: string,
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>,
  signal?: AbortSignal
): Promise<void> {
  const tokens = fullText.match(/(\S+|\s+)/g) || [fullText];
  const total = tokens.length;
  if (total <= 1) {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === botMsgId ? { ...msg, content: fullText, isStreaming: false } : msg
      )
    );
    return;
  }

  // Adjust chunk size for longer messages to maintain responsiveness
  const chunkSize = total > 400 ? 3 : total > 150 ? 2 : 1;
  const delayMs = 15;

  let currentIdx = 0;
  let accumulated = "";

  return new Promise((resolve) => {
    const timer = setInterval(() => {
      if (signal?.aborted || currentIdx >= total) {
        clearInterval(timer);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === botMsgId ? { ...msg, content: fullText, isStreaming: false } : msg
          )
        );
        resolve();
        return;
      }

      for (let i = 0; i < chunkSize && currentIdx < total; i++) {
        accumulated += tokens[currentIdx];
        currentIdx++;
      }

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === botMsgId ? { ...msg, content: accumulated, isStreaming: true } : msg
        )
      );
    }, delayMs);
  });
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Track conversation_id for multi-turn memory (set after first response)
  const conversationIdRef = useRef<string | null>(null);

  const sendMessage = useCallback(async (text: string, files: File[], token?: string | null) => {
    const trimmed = text.trim();
    if (!trimmed && files.length === 0) return;
    if (isLoading) return;

    // Add user message immediately
    const userMsg: ChatMessage = {
      id: uid(),
      role: "user",
      content: trimmed,
      timestamp: new Date(),
      attachmentNames: files.map((f) => f.name),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const data = await postChat(trimmed, files, conversationId, token);
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
        setConversationId(data.conversation_id);
      }

      const botContent = buildBotContent(
        data.success,
        data.message,
        data.assistant_message ?? null,
        data.warnings ?? [],
        data.attachment_statuses ?? []
      );

      const botMsgId = uid();
      const shouldStream = data.success && Boolean(data.assistant_message?.content) && botContent.length > 20;

      const botMsg: ChatMessage = {
        id: botMsgId,
        role: "bot",
        content: shouldStream ? "" : botContent,
        isStreaming: shouldStream,
        timestamp: new Date(),
        attachmentStatuses: data.attachment_statuses ?? [],
        warnings: (data.warnings ?? []).map((w) =>
          safeText(w.message, "The request was processed with a warning.")
        ),
        isError: !data.success,
      };

      setMessages((prev) => [...prev, botMsg]);
      setIsLoading(false);

      if (shouldStream) {
        abortRef.current = new AbortController();
        await streamBotResponse(botMsgId, botContent, setMessages, abortRef.current.signal);
      }
    } catch {
      const errorMsg: ChatMessage = {
        id: uid(),
        role: "bot",
        content:
          "I couldn't reach the helpdesk server. Please make sure the FastAPI backend is running on port 8000 and try again.",
        timestamp: new Date(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, conversationId]);

  const loadThread = useCallback(async (threadId: string, token: string) => {
    setIsLoading(true);
    try {
      const threadMessages = await fetchThreadMessages(threadId, token);
      const converted: ChatMessage[] = threadMessages.map((m) => ({
        id: m.id || uid(),
        role: m.role === "ai" ? "bot" : "user",
        content: m.content,
        timestamp: m.created_at ? new Date(m.created_at) : new Date(),
      }));
      setMessages(converted.length > 0 ? converted : [WELCOME_MESSAGE]);
      setConversationId(threadId);
    } catch (err) {
      console.error("Failed to load thread messages:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([{ ...WELCOME_MESSAGE, timestamp: new Date() }]);
    setIsLoading(false);
    setPendingQuery("");
    conversationIdRef.current = null;
    setConversationId(null);
  }, []);

  return { messages, isLoading, pendingQuery, conversationId, sendMessage, loadThread, clearChat, setPendingQuery };
}
