"use client";

import { useState } from "react";
import styles from "./page.module.css";
import Sidebar from "@/components/Sidebar";
import ChatWindow from "@/components/ChatWindow";
import RightPanel from "@/components/RightPanel";
import { useChat } from "@/hooks/useChat";

export default function Home() {
  const { messages, isLoading, pendingQuery, sendMessage, clearChat, setPendingQuery } = useChat();
  const [panelCollapsed, setPanelCollapsed] = useState(false);

  const handleSuggestedQuestion = (q: string) => {
    // Send directly to chat — no composer prefill needed
    sendMessage(q, []);
  };

  return (
    <div className={styles.shell}>
      <Sidebar onNewChat={clearChat} />
      <ChatWindow
        messages={messages}
        isLoading={isLoading}
        pendingQuery={pendingQuery}
        onSend={sendMessage}
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
