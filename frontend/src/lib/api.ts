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
};

export type ProcessingWarning = {
  code?: string;
  message?: string;
};

export type ChatApiResponse = {
  success: boolean;
  message: string;
  attachment_statuses: AttachmentStatus[];
  warnings: ProcessingWarning[];
  normalized_input: unknown;
};

/**
 * Send a chat message (with optional file attachments) to the backend.
 * Throws on network failure; returns the parsed JSON body otherwise.
 */
export async function postChat(
  message: string,
  files: File[]
): Promise<ChatApiResponse> {
  const form = new FormData();

  const trimmed = message.trim();
  if (trimmed) {
    form.append("message", trimmed);
  }

  for (const file of files) {
    form.append("files", file);
  }

  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    body: form,
  });

  // Parse body regardless of HTTP status so we can surface API error messages.
  const data = await response.json().catch(() => ({})) as ChatApiResponse;
  return data;
}
