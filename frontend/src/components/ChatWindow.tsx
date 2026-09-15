"use client";

import { useEffect, useRef } from "react";
import styles from "./ChatWindow.module.css";
import MessageBubble from "./MessageBubble";
import TypingIndicator from "./TypingIndicator";
import Composer from "./Composer";
import type { ChatMessage } from "@/hooks/useChat";

type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
  pendingQuery: string;
  onSend: (text: string, files: File[]) => Promise<void>;
  onPendingQueryChange: (q: string) => void;
};

export default function ChatWindow({ messages, isLoading, pendingQuery, onSend, onPendingQueryChange }: Props) {
  const transcriptRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    const el = transcriptRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <main className={styles.window} aria-label="Chat conversation">
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.botAvatar} aria-hidden>
            <BotIcon />
          </div>
          <div>
            <h1 className={styles.headerTitle}>Government Helpdesk Assistant</h1>
            <p className={styles.headerSub}>
              <span className={styles.onlineDot} />
              Ask about government documents, procedures, eligibility and more.
            </p>
          </div>
        </div>
      </header>

      {/* Transcript */}
      <div className={styles.transcript} ref={transcriptRef} aria-live="polite" aria-label="Conversation transcript">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isLoading && <TypingIndicator />}
      </div>

      {/* Composer */}
      <Composer
        onSend={onSend}
        isLoading={isLoading}
        initialValue={pendingQuery}
        onValueChange={onPendingQueryChange}
      />
    </main>
  );
}

function BotIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="10" rx="2"/>
      <path d="M12 11V6"/>
      <circle cx="12" cy="4" r="2"/>
      <path d="M8 15h.01M16 15h.01"/>
    </svg>
  );
}
