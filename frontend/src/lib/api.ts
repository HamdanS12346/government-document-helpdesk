/**
 * API client for the Government Helpdesk backend.
 * Endpoint: POST http://localhost:8000/chat
 * Content-Type: multipart/form-data
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AttachmentStatus = {
  filename?: string;
  status?: "success" | "failed" | "skipped";
  error?: { message?: string } | null;
  warnings?: ProcessingWarning[];
};

export type ProcessingWarning = {
  code?: string;
  message?: string;
};

export type AssistantMessage = {
  role: "assistant";
  content: string;
};

export type ChatApiResponse = {
  success: boolean;
  status:
    | "completed"
    | "clarification_required"
    | "input_failed"
    | "classification_error"
    | "system_error"
    | string;
  message: string;
  assistant_message: AssistantMessage | null;
  attachment_statuses: AttachmentStatus[];
  warnings: ProcessingWarning[];
  normalized_input: unknown;
  intent: {
    type: string;
    confidence_score: number | null;
  } | null;
  conversation_id: string | null;
};

export type ThreadItem = {
  id: string;
  title: string | null;
  conversation_summary: string;
  created_at: string | null;
  updated_at: string | null;
};

export type ThreadMessage = {
  id?: string;
  thread_id: string;
  role: "human" | "ai" | "system";
  content: string;
  sequence_number: number;
  created_at?: string | null;
};

/**
 * Send a chat message (with optional file attachments) to the backend.
 * Throws on network failure; returns the parsed JSON body otherwise.
 */
export async function postChat(
  message: string,
  files: File[],
  conversationId?: string | null,
  token?: string | null
): Promise<ChatApiResponse> {
  const form = new FormData();

  const trimmed = message.trim();
  if (trimmed) {
    form.append("message", trimmed);
  }

  for (const file of files) {
    form.append("files", file);
  }

  if (conversationId) {
    form.append("conversation_id", conversationId);
  }

  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers,
    body: form,
  });

  // Parse body regardless of HTTP status so we can surface API error messages.
  const data = (await response.json().catch(() => ({}))) as ChatApiResponse;
  return data;
}

/**
 * Fetch past conversation threads for the authenticated user.
 */
export async function fetchUserThreads(token: string): Promise<ThreadItem[]> {
  const response = await fetch(`${API_BASE}/threads`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const errData = (await response.json().catch(() => ({}))) as { detail?: string };
    const message = errData.detail || response.statusText;
    throw new Error(`Failed to fetch threads: ${message}`);
  }
  return response.json();
}

/**
 * Fetch full transcript of messages for an owned conversation thread.
 */
export async function fetchThreadMessages(
  threadId: string,
  token: string
): Promise<ThreadMessage[]> {
  const response = await fetch(`${API_BASE}/threads/${threadId}/messages`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const errData = (await response.json().catch(() => ({}))) as { detail?: string };
    const message = errData.detail || response.statusText;
    throw new Error(`Failed to fetch thread messages: ${message}`);
  }
  return response.json();
}

/**
 * Delete an owned conversation thread from history.
 */
export async function deleteUserThread(
  threadId: string,
  token: string
): Promise<boolean> {
  const response = await fetch(`${API_BASE}/threads/${threadId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return response.ok;
}
