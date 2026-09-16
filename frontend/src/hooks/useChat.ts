"use client";

import { useCallback, useRef, useState } from "react";
import {
  postChat,
  fetchThreadMessages,
  type AttachmentStatus,
  type ChatApiResponse,
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
  data: ChatApiResponse
): string {
  const warnings = data.warnings ?? [];
  const attachmentStatuses = data.attachment_statuses ?? [];
  const assistantContent = data.assistant_message?.content;

  if (!data.success) {
    return safeText(
      data.message,
      "Sorry, I couldn't process that request. Please try again."
    );
  }

  const failedFiles = attachmentStatuses.filter((s) => s.status === "failed");
  if (failedFiles.length > 0 && attachmentStatuses.every((s) => s.status === "failed")) {
    return "I received your message but couldn't process the attached files. Please check that they are valid PDF, PNG, or JPEG files.";
  }

  let reply = assistantContent
    ? safeText(assistantContent, data.message)
    : "Thank you! I've received and processed your request successfully.";

  if (attachmentStatuses.length > 0) {
    const ok = attachmentStatuses.filter((s) => s.status === "success").length;
    reply += ` ${ok} of ${attachmentStatuses.length} attachment${attachmentStatuses.length > 1 ? "s" : ""} processed.`;
  }
  if (warnings.length > 0) {
    reply += "\n\n⚠️ Note: " + warnings.map((w) => safeText(w.message, "Processing warning.")).join("; ");
  }
  return reply;
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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
        setConversationId(data.conversation_id);
      }

      const botMsg: ChatMessage = {
        id: uid(),
        role: "bot",
        content: buildBotContent(data),
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
    setConversationId(null);
  }, []);

  return { messages, isLoading, pendingQuery, conversationId, sendMessage, loadThread, clearChat, setPendingQuery };
}
