import styles from "./MessageBubble.module.css";
import FileChip from "./FileChip";
import type { ChatMessage } from "@/hooks/useChat";

type Props = {
  message: ChatMessage;
};

function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
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

function UserIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>
  );
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  /* Render content with newlines preserved */
  const renderContent = (text: string) =>
    text.split("\n").map((line, i) =>
      line ? <p key={i}>{line}</p> : <br key={i} />
    );

  return (
    <div className={`${styles.wrapper} ${isUser ? styles.user : styles.bot}`}>
      {/* Avatar */}
      {!isUser && (
        <div className={styles.avatar} aria-hidden>
          <BotIcon />
        </div>
      )}

      <div className={styles.contentCol}>
        {/* Role label */}
        <span className={styles.roleLabel}>
          {isUser ? "You" : "Government Helpdesk Assistant"}
        </span>

        {/* Bubble */}
        <div className={`${styles.bubble} ${message.isError ? styles.errorBubble : ""}`}>
          <div className={styles.text}>{renderContent(message.content)}</div>

          {/* Attached file chips (user messages) */}
          {message.attachmentNames && message.attachmentNames.length > 0 && (
            <div className={styles.chips}>
              {message.attachmentNames.map((name) => (
                <FileChip key={name} name={name} />
              ))}
            </div>
          )}
        </div>

        {/* Timestamp */}
        <time className={styles.timestamp} dateTime={message.timestamp.toISOString()} suppressHydrationWarning>
          {formatTime(message.timestamp)}
        </time>
      </div>

      {/* User avatar */}
      {isUser && (
        <div className={`${styles.avatar} ${styles.userAvatar}`} aria-hidden>
          <UserIcon />
        </div>
      )}
    </div>
  );
}
