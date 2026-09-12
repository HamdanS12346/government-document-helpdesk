"use client";

import { useState } from "react";
import styles from "./page.module.css";

export default function Home() {
  const [message, setMessage] = useState("");
  const [selectedFileNames, setSelectedFileNames] = useState<string[]>([]);
  const [formError, setFormError] = useState("");

  const hasRequestContent =
    message.trim().length > 0 || selectedFileNames.length > 0;

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    setSelectedFileNames(files.map((file) => file.name));
    if (files.length > 0) {
      setFormError("");
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!hasRequestContent) {
      setFormError("Enter a message or attach a supported file before sending.");
      return;
    }

    setFormError("");
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
          <div className={styles.actions}>
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={!hasRequestContent}
            >
              Send
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
