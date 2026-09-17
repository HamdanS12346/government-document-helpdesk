"use client";

import { useEffect, useState } from "react";
import styles from "./TypingIndicator.module.css";

const STATUS_STAGES = [
  "Analyzing request & documents...",
  "Consulting official government databases...",
  "Cross-checking eligibility & guidelines...",
  "Verifying citations & formulating response...",
];

export default function TypingIndicator() {
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStageIndex((prev) => (prev + 1) % STATUS_STAGES.length);
    }, 2400);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className={styles.wrapper} aria-label="Assistant is generating a response" role="status">
      <div className={styles.avatar} aria-hidden>
        <BotIcon />
        <span className={styles.avatarPulse} />
      </div>
      <div className={styles.bubble}>
        <div className={styles.header}>
          <div className={styles.equalizer} aria-hidden>
            <span className={styles.bar} />
            <span className={styles.bar} />
            <span className={styles.bar} />
            <span className={styles.bar} />
          </div>
          <span className={styles.stageText} key={stageIndex}>
            {STATUS_STAGES[stageIndex]}
          </span>
        </div>
        <div className={styles.progressBar}>
          <div className={styles.progressShimmer} />
        </div>
      </div>
    </div>
  );
}

function BotIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="10" rx="2"/>
      <path d="M12 11V6"/>
      <circle cx="12" cy="4" r="2"/>
      <path d="M8 15h.01M16 15h.01"/>
    </svg>
  );
}
