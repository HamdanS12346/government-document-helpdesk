"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import styles from "./Composer.module.css";
import FileChip from "./FileChip";
import {
  ACCEPTED_UPLOAD_HINT,
  ACCEPTED_UPLOAD_TYPES,
  ATTACH_TOOLTIP,
} from "@/lib/attachmentUi";

type Props = {
  onSend: (text: string, files: File[]) => Promise<void>;
  isLoading: boolean;
  initialValue?: string;
  onValueChange?: (v: string) => void;
};

export default function Composer({ onSend, isLoading, initialValue = "", onValueChange }: Props) {
  const [text, setText] = useState(initialValue);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Keep in sync if parent sets initial value
  const handleTextChange = (val: string) => {
    setText(val);
    onValueChange?.(val);
    setError("");
    // Auto-grow
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    setFiles((prev) => [...prev, ...selected]);
    setError("");
    e.target.value = "";
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSend = async () => {
    if (isLoading) return;
    if (!text.trim() && files.length === 0) {
      setError("Enter a message or attach a file before sending.");
      return;
    }
    const messageText = text;
    const messageFiles = files;
    setText("");
    setFiles([]);
    setError("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await onSend(messageText, messageFiles);
  };

  const canSend = (text.trim().length > 0 || files.length > 0) && !isLoading;

  return (
    <div className={styles.outer}>
      {/* File chip row */}
      {files.length > 0 && (
        <div className={styles.fileRow}>
          {files.map((f, i) => (
            <FileChip key={`${f.name}-${i}`} name={f.name} onRemove={() => removeFile(i)} />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className={styles.error} role="alert">{error}</p>
      )}

      {/* Input bar */}
      <div className={`${styles.bar} ${isLoading ? styles.barLoading : ""}`}>
        {/* Attach button */}
        <button
          type="button"
          className={styles.attachBtn}
          aria-label="Attach file"
          title={ATTACH_TOOLTIP}
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
        >
          <PaperclipIcon />
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_UPLOAD_TYPES}
          multiple
          className={styles.hiddenInput}
          onChange={handleFileChange}
          aria-hidden
          tabIndex={-1}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          id="chat-input"
          className={styles.textarea}
          value={text}
          onChange={(e) => handleTextChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your question here…"
          rows={1}
          disabled={isLoading}
          aria-label="Chat message"
          aria-describedby={error ? "composer-error" : undefined}
        />

        {/* Send button */}
        <button
          type="button"
          className={`${styles.sendBtn} ${canSend ? styles.sendBtnActive : ""}`}
          aria-label="Send message"
          onClick={handleSend}
          disabled={!canSend}
        >
          {isLoading ? <SpinnerIcon /> : <SendIcon />}
        </button>
      </div>

      <p className={styles.hint}>
        Press <kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for new line · {ACCEPTED_UPLOAD_HINT}
      </p>
    </div>
  );
}

function PaperclipIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"/>
      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: "spin 0.8s linear infinite" }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  );
}
