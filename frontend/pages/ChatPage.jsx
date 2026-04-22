import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";
import Header from "../components/Header";

export default function ChatPage() {
  return (
    <div className="chat-layout">
      <Sidebar />
      <main className="content">
        <Header />
        <ChatWindow />
      </main>
    </div>
  );
}
