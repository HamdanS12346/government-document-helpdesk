"use client";

import React, { useCallback, useEffect, useState } from "react";
import styles from "./Sidebar.module.css";
import { useAuth } from "../hooks/useAuth";
import { AuthModal } from "./AuthModal";
import { fetchUserThreads, deleteUserThread, type ThreadItem } from "../lib/api";

type Props = {
  onNewChat: () => void;
  activeThreadId?: string | null;
  onSelectThread?: (threadId: string) => void;
};

export default function Sidebar({ onNewChat, activeThreadId, onSelectThread }: Props) {
  const { user, token, signOut } = useAuth();
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [threads, setThreads] = useState<ThreadItem[]>([]);

  const loadThreads = useCallback(async () => {
    if (!token) {
      setThreads([]);
      return;
    }
    try {
      const items = await fetchUserThreads(token);
      setThreads(items);
    } catch (err) {
      console.warn("Could not load user threads:", err);
      setThreads([]);
    }
  }, [token]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads, activeThreadId]);

  const handleDelete = async (e: React.MouseEvent, threadId: string) => {
    e.stopPropagation();
    if (!token) return;
    const ok = await deleteUserThread(threadId, token);
    if (ok) {
      setThreads((prev) => prev.filter((t) => t.id !== threadId));
      if (activeThreadId === threadId) {
        onNewChat();
      }
    }
  };

  const handleSignOut = async () => {
    await signOut();
    setThreads([]);
    onNewChat();
  };

  return (
    <>
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

        {/* User Authentication Status */}
        <div className={styles.userSection}>
          {user ? (
            <div className={styles.userCard}>
              <div className={styles.userInfo}>
                <div className={styles.userAvatar}>
                  {user.email ? user.email[0].toUpperCase() : "U"}
                </div>
                <span className={styles.userEmail} title={user.email || ""}>
                  {user.email}
                </span>
              </div>
              <button
                type="button"
                className={styles.signOutBtn}
                onClick={handleSignOut}
                title="Sign out"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <button
              type="button"
              className={styles.signInBtn}
              onClick={() => setIsAuthModalOpen(true)}
            >
              <UserIcon />
              <span>Sign In / Register</span>
            </button>
          )}
        </div>

        {/* Navigation & History */}
        <nav className={styles.nav}>
          <button
            id="new-chat"
            className={`${styles.navItem} ${styles.newChatBtn}`}
            onClick={onNewChat}
            type="button"
          >
            <PlusIcon />
            <span>New Consultation</span>
          </button>

          {/* Conversation History for Authenticated Citizens */}
          {user && threads.length > 0 && (
            <div className={styles.historySection}>
              <div className={styles.historyHeader}>Past Consultations</div>
              {threads.map((t) => {
                const isActive = activeThreadId === t.id;
                const formattedDate = t.updated_at
                  ? new Date(t.updated_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })
                  : "";

                return (
                  <div
                    key={t.id}
                    className={`${styles.threadItem} ${isActive ? styles.threadItemActive : ""}`}
                  >
                    <button
                      type="button"
                      className={styles.threadContentBtn}
                      onClick={() => onSelectThread?.(t.id)}
                    >
                      <span className={styles.threadTitle} title={t.title || "Consultation"}>
                        {t.title || "Consultation"}
                      </span>
                      {formattedDate && <span className={styles.threadDate}>{formattedDate}</span>}
                    </button>
                    <button
                      type="button"
                      className={styles.threadDeleteBtn}
                      onClick={(e) => handleDelete(e, t.id)}
                      title="Delete consultation"
                      aria-label="Delete consultation"
                    >
                      <TrashIcon />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <button
            id="documents"
            className={`${styles.navItem} ${styles.navItemDisabled}`}
            disabled
            type="button"
            title="Coming soon"
          >
            <FolderIcon />
            <span>Document Library</span>
            <span className={styles.soon}>Soon</span>
          </button>

          <button
            id="about"
            className={`${styles.navItem} ${styles.navItemDisabled}`}
            disabled
            type="button"
            title="Coming soon"
          >
            <InfoIcon />
            <span>About the Service</span>
            <span className={styles.soon}>Soon</span>
          </button>
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

      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => {
          setIsAuthModalOpen(false);
          loadThreads();
        }}
      />
    </>
  );
}

/* ---- Icons ---- */
function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function EmblemIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="6" stroke="currentColor" strokeWidth="1" strokeDasharray="2 2" />
      <circle cx="12" cy="12" r="2" fill="currentColor" />
      <line x1="12" y1="2" x2="12" y2="6" stroke="currentColor" strokeWidth="1.5" />
      <line x1="12" y1="18" x2="12" y2="22" stroke="currentColor" strokeWidth="1.5" />
      <line x1="2" y1="12" x2="6" y2="12" stroke="currentColor" strokeWidth="1.5" />
      <line x1="18" y1="12" x2="22" y2="12" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function EmblemSmall() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0, opacity: 0.7 }}>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </svg>
  );
}
