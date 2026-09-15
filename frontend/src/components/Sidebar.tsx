"use client";

import styles from "./Sidebar.module.css";

type Props = {
  onNewChat: () => void;
};

const NAV_ITEMS = [
  {
    id: "new-chat",
    label: "New Chat",
    icon: <PlusIcon />,
    isAction: true,
  },
  {
    id: "conversations",
    label: "My Conversations",
    icon: <ChatIcon />,
    disabled: true,
  },
  {
    id: "documents",
    label: "Document Library",
    icon: <FolderIcon />,
    disabled: true,
  },
  {
    id: "about",
    label: "About the Service",
    icon: <InfoIcon />,
    disabled: true,
  },
];

export default function Sidebar({ onNewChat }: Props) {
  return (
    <aside className={styles.sidebar} aria-label="Navigation">
      {/* Brand */}
      <div className={styles.brand}>
        <div className={styles.emblem} aria-hidden>
          <EmblemIcon />
        </div>
        <div>
          <p className={styles.brandName}>Government Helpdesk</p>
          <p className={styles.brandTagline}>Your Questions. Our Information.</p>
        </div>
      </div>

      {/* Nav */}
      <nav className={styles.nav}>
        {NAV_ITEMS.map((item) => {
          if (item.isAction) {
            return (
              <button
                key={item.id}
                id={item.id}
                className={`${styles.navItem} ${styles.newChatBtn}`}
                onClick={onNewChat}
                type="button"
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            );
          }
          return (
            <button
              key={item.id}
              id={item.id}
              className={`${styles.navItem} ${item.disabled ? styles.navItemDisabled : ""}`}
              disabled={item.disabled}
              type="button"
              title={item.disabled ? "Coming soon" : undefined}
            >
              {item.icon}
              <span>{item.label}</span>
              {item.disabled && <span className={styles.soon}>Soon</span>}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className={styles.footer}>
        <EmblemSmall />
        <div>
          <p className={styles.footerTitle}>Government of India</p>
          <p className={styles.footerSub}>Digital India · Citizen First</p>
        </div>
      </div>
    </aside>
  );
}

/* ---- Icons ---- */
function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  );
}
function ChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
    </svg>
  );
}
function FolderIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
    </svg>
  );
}
function InfoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>
  );
}
function EmblemIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
    </svg>
  );
}
function EmblemSmall() {
  return (
    <div style={{ opacity: 0.6 }}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9"/>
        <path d="M12 3v4M12 17v4M3 12h4M17 12h4"/>
      </svg>
    </div>
  );
}
