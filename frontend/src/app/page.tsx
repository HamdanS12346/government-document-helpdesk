"use client";

import { useRef, useState } from "react";
import styles from "./page.module.css";

type ChatResponse = {
  success?: boolean;
  message?: string;
  attachment_statuses?: AttachmentStatus[];
  warnings?: ProcessingWarning[];
};

type ProcessingWarning = {
  code?: string;
  message?: string;
};

type AttachmentStatus = {
  filename?: string;
  status?: string;
  error?: {
    message?: string;
  } | null;
};

function safeDisplayMessage(message: string | undefined, fallback: string) {
  if (!message) {
    return fallback;
  }

  const unsafePatterns = [
    "Traceback",
    "File \"",
    "site-packages",
    "RuntimeError",
    "Exception",
  ];

  return unsafePatterns.some((pattern) => message.includes(pattern))
    ? fallback
    : message;
}

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState("");
  const [selectedFileNames, setSelectedFileNames] = useState<string[]>([]);
  const [formError, setFormError] = useState("");
  const [formReadyMessage, setFormReadyMessage] = useState("");
  const [submitStatus, setSubmitStatus] = useState("");
  const [submitFailed, setSubmitFailed] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [attachmentErrors, setAttachmentErrors] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const hasRequestContent =
    message.trim().length > 0 || selectedFileNames.length > 0;

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    setSelectedFileNames(files.map((file) => file.name));
    setFormReadyMessage("");
    setSubmitStatus("");
    setSubmitFailed(false);
    setWarnings([]);
    setAttachmentErrors([]);
    if (files.length > 0) {
      setFormError("");
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (!hasRequestContent) {
      setFormError("Enter a message or attach a supported file before sending.");
      return;
    }

    const formData = new FormData();
    const trimmedMessage = message.trim();
    if (trimmedMessage) {
      formData.append("message", trimmedMessage);
    }

    const submittedFormData = new FormData(event.currentTarget);
    const selectedFiles = submittedFormData
      .getAll("files")
      .filter((entry): entry is File => entry instanceof File && entry.size > 0);
    selectedFiles.forEach((file) => {
      formData.append("files", file);
    });
    const fileCount = selectedFiles.length;
    setFormReadyMessage(
      `Request ready with ${fileCount} attachment${fileCount === 1 ? "" : "s"}.`,
    );

    setFormError("");
    setSubmitStatus("");
    setSubmitFailed(false);
    setWarnings([]);
    setAttachmentErrors([]);
    setIsSubmitting(true);

    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        body: formData,
      });
      const result = (await response.json().catch(() => ({}))) as ChatResponse;
      const failedAttachmentMessages = (result.attachment_statuses ?? [])
        .filter(
          (status) =>
            status.status === "failed" && status.error?.message !== undefined,
        )
        .map((status) =>
          status.filename
            ? `${status.filename}: ${safeDisplayMessage(
                status.error?.message,
                "Attachment could not be processed.",
              )}`
            : safeDisplayMessage(
                status.error?.message,
                "Attachment could not be processed.",
            ),
        );
      const safeWarnings = (result.warnings ?? []).map((warning) =>
        safeDisplayMessage(warning.message, "The request was processed with a warning."),
      );

      const wasSuccessful = response.ok && result.success === true;
      setSubmitStatus(
        wasSuccessful
          ? "Input processed successfully."
          : safeDisplayMessage(result.message, "Input could not be processed."),
      );
      setSubmitFailed(!wasSuccessful);
      setWarnings(safeWarnings);
      setAttachmentErrors(failedAttachmentMessages);
      if (wasSuccessful) {
        setMessage("");
      }
    } catch {
      setSubmitStatus(
        "The helpdesk server is not reachable. Start FastAPI and try again.",
      );
      setSubmitFailed(true);
      setWarnings([]);
      setAttachmentErrors([]);
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setSelectedFileNames([]);
      setIsSubmitting(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.chatShell} aria-label="Government document helpdesk chat">
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Government Document Helpdesk</p>
            <h1>Document chat</h1>
          </div>
          <span className={styles.status}>Input Processor</span>
        </header>

        <div className={styles.transcript} aria-live="polite">
          <article className={styles.message}>
            <p className={styles.messageLabel}>Assistant</p>
            <p>
              Send a question or attach a government document to prepare it for
              processing.
            </p>
          </article>
        </div>

        <form className={styles.composer} onSubmit={handleSubmit}>
          <label className={styles.label} htmlFor="message">
            Message
          </label>
          <textarea
            className={styles.textarea}
            id="message"
            name="message"
            value={message}
            onChange={(event) => {
              setMessage(event.target.value);
              setFormReadyMessage("");
              setSubmitStatus("");
              setSubmitFailed(false);
              setWarnings([]);
              setAttachmentErrors([]);
              if (event.target.value.trim().length > 0) {
                setFormError("");
              }
            }}
            rows={4}
            placeholder="Ask about a notice, benefit letter, form, or uploaded document."
          />
          <label className={styles.fileControl} htmlFor="files">
            <span>Attachments</span>
            <input
              className={styles.fileInput}
              id="files"
              name="files"
              type="file"
              ref={fileInputRef}
              accept=".png,.jpg,.jpeg,.pdf"
              multiple
              onChange={handleFileChange}
            />
          </label>
          {selectedFileNames.length > 0 ? (
            <div className={styles.selectedFiles} aria-live="polite">
              <p className={styles.selectedFilesLabel}>Selected files</p>
              <ul>
                {selectedFileNames.map((fileName) => (
                  <li key={fileName}>{fileName}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {formError ? (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          ) : null}
          {formReadyMessage ? (
            <p className={styles.formReady} role="status">
              {formReadyMessage}
            </p>
          ) : null}
          {submitStatus ? (
            <p
              className={submitFailed ? styles.submitError : styles.formReady}
              role={submitFailed ? "alert" : "status"}
            >
              {submitStatus}
            </p>
          ) : null}
          {attachmentErrors.length > 0 ? (
            <div className={styles.attachmentErrors} role="alert">
              <p className={styles.attachmentErrorsLabel}>Attachment issues</p>
              <ul>
                {attachmentErrors.map((attachmentError) => (
                  <li key={attachmentError}>{attachmentError}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className={styles.warningList} role="status">
              <p className={styles.warningListLabel}>Warnings</p>
              <ul>
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {isSubmitting ? (
            <p className={styles.formReady} role="status">
              Processing request...
            </p>
          ) : null}
          <div className={styles.actions}>
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Sending" : "Send"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
