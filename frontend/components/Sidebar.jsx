import { useNavigate, useLocation } from "react-router-dom";
import { useChat } from "../src/ChatContext";

export default function Sidebar() {
  const { resetChat } = useChat();
  const navigate = useNavigate();
  const location = useLocation();
  const name = localStorage.getItem("name") || "User";

  const logout = () => {
    localStorage.clear();
    resetChat();
    navigate("/login");
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>SAFAR AI</h1>
        <p>Hello, {name}</p>
      </div>
      
      <nav className="sidebar-nav">
        <button 
          className={location.pathname === "/chat" ? "active" : ""} 
          onClick={() => navigate("/chat")}
        >
          Chat
        </button>
        <button 
          className={location.pathname === "/history" ? "active" : ""} 
          onClick={() => navigate("/history")}
        >
          History
        </button>
      </nav>

      <div className="sidebar-footer">
        <button className="logout-btn" onClick={logout}>Logout</button>
      </div>
    </aside>
  );
}
