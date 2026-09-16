"use client";

import { useState } from "react";
import styles from "./page.module.css";
import Sidebar from "@/components/Sidebar";
import ChatWindow from "@/components/ChatWindow";
import RightPanel from "@/components/RightPanel";
import { useChat } from "@/hooks/useChat";
import { useAuth } from "@/hooks/useAuth";

export default function Home() {
  const {
    messages,
    isLoading,
    pendingQuery,
    conversationId,
    sendMessage,
    loadThread,
    clearChat,
    setPendingQuery,
  } = useChat();
  const { token } = useAuth();
  const [panelCollapsed, setPanelCollapsed] = useState(false);

  const handleSend = async (text: string, files: File[]) => {
    await sendMessage(text, files, token);
  };

  const handleSuggestedQuestion = async (q: string) => {
    await sendMessage(q, [], token);
  };

  const handleSelectThread = (threadId: string) => {
    if (token) {
      loadThread(threadId, token);
    }
  };

  return (
    <div className={styles.shell}>
      <Sidebar
        onNewChat={clearChat}
        activeThreadId={conversationId}
        onSelectThread={handleSelectThread}
      />
      <ChatWindow
        messages={messages}
        isLoading={isLoading}
        pendingQuery={pendingQuery}
        onSend={handleSend}
        onPendingQueryChange={setPendingQuery}
      />
      <RightPanel
        onSuggestedQuestion={handleSuggestedQuestion}
        collapsed={panelCollapsed}
        onToggle={() => setPanelCollapsed((prev) => !prev)}
      />
    </div>
  );
}
