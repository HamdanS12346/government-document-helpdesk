"use client";

import { useCallback, useRef, useState } from "react";
import {
  postChat,
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
};

type UseChatReturn = {
  messages: ChatMessage[];
  isLoading: boolean;
  pendingQuery: string;
  conversationId: string | null;
  sendMessage: (text: string, files: File[]) => Promise<void>;
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

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Track conversation_id for multi-turn memory (set after first response)
  const conversationIdRef = useRef<string | null>(null);

  const sendMessage = useCallback(async (text: string, files: File[]) => {
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
      const activeConversationId = conversationIdRef.current || conversationId;
      const data = await postChat(trimmed, files, activeConversationId);

      // Persist the conversation_id returned by the backend for session memory.
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
        setConversationId(data.conversation_id);
      }

      const botMsg: ChatMessage = {
        id: uid(),
        role: "bot",
        content: buildBotContent(
          data.success,
          data.message,
          data.assistant_message ?? null,
          data.warnings ?? [],
          data.attachment_statuses ?? []
        ),
        timestamp: new Date(),
        attachmentStatuses: data.attachment_statuses ?? [],
        warnings: (data.warnings ?? []).map((w) =>
          safeText(w.message, "The request was processed with a warning.")
        ),
        isError: !data.success,
      };
      setMessages((prev) => [...prev, botMsg]);
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

  const clearChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([{ ...WELCOME_MESSAGE, timestamp: new Date() }]);
    setIsLoading(false);
    setPendingQuery("");
    conversationIdRef.current = null;
    setConversationId(null);
  }, []);

  return { messages, isLoading, pendingQuery, conversationId, sendMessage, clearChat, setPendingQuery };
}
