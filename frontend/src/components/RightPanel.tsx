"use client";

import { useState } from "react";
import styles from "./RightPanel.module.css";

const SUGGESTED_QUESTIONS = [
  "How can I get a PAN card?",
  "What are the documents required for Aadhaar?",
  "Steps to apply for a residence certificate?",
  "How to renew a driving licence?",
  "What is the procedure for a marriage certificate?",
  "How to apply for an old age pension?",
  "How do I check my EPF balance?",
  "What documents are needed for a passport application?",
  "How to register a property in India?",
  "What is the process for obtaining a birth certificate?",
];

type Props = {
  onSuggestedQuestion: (q: string) => void;
  collapsed: boolean;
  onToggle: () => void;
};

export default function RightPanel({ onSuggestedQuestion, collapsed, onToggle }: Props) {
  return (
    <aside
      className={`${styles.panel} ${collapsed ? styles.collapsed : ""}`}
      aria-label="Suggested questions"
    >
      {/* Toggle button — always visible */}
      <button
        className={styles.toggleBtn}
        onClick={onToggle}
        type="button"
        aria-label={collapsed ? "Expand suggestions panel" : "Collapse suggestions panel"}
        title={collapsed ? "Show suggested questions" : "Hide suggested questions"}
      >
        <ChevronIcon flipped={collapsed} />
      </button>

      {/* Panel content — hidden when collapsed */}
      <div className={styles.content} aria-hidden={collapsed}>
        <div className={styles.header}>
          <LightbulbIcon />
          <h2 className={styles.title}>Suggested Questions</h2>
        </div>

        <p className={styles.hint}>Click a question to send it directly to the assistant.</p>

        <ul className={styles.list}>
          {SUGGESTED_QUESTIONS.map((q) => (
            <li key={q}>
              <button
                className={styles.questionBtn}
                type="button"
                onClick={() => onSuggestedQuestion(q)}
                tabIndex={collapsed ? -1 : 0}
              >
                <span className={styles.questionText}>{q}</span>
                <SendSmallIcon />
              </button>
            </li>
          ))}
        </ul>

        {/* Privacy notice */}
        <div className={styles.privacy}>
          <ShieldIcon />
          <p className={styles.privacyText}>
            Conversations are secure and confidential. We do not store personal information.
          </p>
        </div>
      </div>
    </aside>
  );
}

/* ---- Icons ---- */
function ChevronIcon({ flipped }: { flipped: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ transform: flipped ? "rotate(180deg)" : "none", transition: "transform 250ms ease" }}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function LightbulbIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="9" y1="18" x2="15" y2="18" />
      <line x1="10" y1="22" x2="14" y2="22" />
      <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0018 8 6 6 0 006 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 018.91 14" />
    </svg>
  );
}

function SendSmallIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
