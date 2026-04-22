import React, { createContext, useContext, useState } from "react";

const ChatContext = createContext();

export function ChatProvider({ children }) {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Welcome to SAFAR AI. Start booking your train tickets." },
  ]);
  const [chatStarted, setChatStarted] = useState(false);

  const resetChat = () => {
    setMessages([
      { role: "assistant", text: "Welcome to SAFAR AI. Start booking your train tickets." },
    ]);
    setChatStarted(false);
  };

  return (
    <ChatContext.Provider value={{ messages, setMessages, chatStarted, setChatStarted, resetChat }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  return useContext(ChatContext);
}
