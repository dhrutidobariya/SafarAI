import React, { createContext, useContext, useState } from "react";

const ChatContext = createContext();

export function ChatProvider({ children }) {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "please share source,destination,date,seat." },
  ]);
  const [chatStarted, setChatStarted] = useState(false);

  const resetChat = () => {
    setMessages([
      { role: "assistant", text: "please share source,destination,date,seat." },
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
