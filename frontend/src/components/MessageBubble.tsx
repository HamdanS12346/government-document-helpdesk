import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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

/** Markdown components map — each element gets a scoped CSS class. */
const markdownComponents = {
  p:          ({ children }: React.PropsWithChildren) => <p className={styles.mdParagraph}>{children}</p>,
  h1:         ({ children }: React.PropsWithChildren) => <h1 className={styles.mdH1}>{children}</h1>,
  h2:         ({ children }: React.PropsWithChildren) => <h2 className={styles.mdH2}>{children}</h2>,
  h3:         ({ children }: React.PropsWithChildren) => <h3 className={styles.mdH3}>{children}</h3>,
  ul:         ({ children }: React.PropsWithChildren) => <ul className={styles.mdList}>{children}</ul>,
  ol:         ({ children }: React.PropsWithChildren) => <ol className={`${styles.mdList} ${styles.mdOrderedList}`}>{children}</ol>,
  li:         ({ children }: React.PropsWithChildren) => <li className={styles.mdListItem}>{children}</li>,
  strong:     ({ children }: React.PropsWithChildren) => <strong className={styles.mdBold}>{children}</strong>,
  em:         ({ children }: React.PropsWithChildren) => <em className={styles.mdItalic}>{children}</em>,
  blockquote: ({ children }: React.PropsWithChildren) => <blockquote className={styles.mdBlockquote}>{children}</blockquote>,
  hr:         () => <hr className={styles.mdHr} />,
  a:          ({ href, children }: React.AnchorHTMLAttributes<HTMLAnchorElement> & React.PropsWithChildren) => (
    <a href={href} className={styles.mdLink} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  code:       ({ inline, children }: { inline?: boolean; children?: React.ReactNode }) =>
    inline
      ? <code className={styles.mdInlineCode}>{children}</code>
      : <code className={styles.mdCodeBlockInner}>{children}</code>,
  pre:        ({ children }: React.PropsWithChildren) => <pre className={styles.mdCodeBlock}>{children}</pre>,
};

/** Bot-only: render content as Markdown using ReactMarkdown + GFM. */
function BotContent({ text }: { text: string }) {
  return (
    <div className={styles.mdBody}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

/** User messages: plain text, newlines preserved. Never parsed as Markdown. */
function UserContent({ text }: { text: string }) {
  return (
    <div className={styles.text}>
      {text.split("\n").map((line, i) =>
        line ? <p key={i}>{line}</p> : <br key={i} />
      )}
    </div>
  );
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`${styles.wrapper} ${isUser ? styles.user : styles.bot}`}>
      {/* Bot avatar */}
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
          {isUser
            ? <UserContent text={message.content} />
            : <BotContent text={message.content} />
          }

          {/* Attached file chips (user messages only) */}
          {message.attachmentNames && message.attachmentNames.length > 0 && (
            <div className={styles.chips}>
              {message.attachmentNames.map((name) => (
                <FileChip key={name} name={name} />
              ))}
            </div>
          )}
        </div>

        {/* Timestamp */}
        <time
          className={styles.timestamp}
          dateTime={message.timestamp.toISOString()}
          suppressHydrationWarning
        >
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
