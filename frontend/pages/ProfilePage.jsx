import React from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import Header from '../components/Header';
import { User, Mail, LogOut, ArrowLeft } from 'lucide-react';
import { useChat } from '../src/ChatContext';

export default function ProfilePage() {
  const { resetChat } = useChat();
  const navigate = useNavigate();
  const name = localStorage.getItem("name") || "N/A";
  const email = localStorage.getItem("email") || "N/A";

  const handleLogout = () => {
    localStorage.clear();
    resetChat();
    navigate('/login');
  };

  return (
    <div className="chat-layout">
      <Sidebar />
      <main className="content">
        <Header />
        <div className="page-padding">
          <div className="profile-container">
            <button className="back-btn" onClick={() => navigate(-1)}>
              <ArrowLeft size={18} /> Back
            </button>
            
            <div className="profile-card">
              <div className="profile-header">
                <div className="profile-avatar large">
                  {name.charAt(0).toUpperCase()}
                </div>
                <h2>Account Details</h2>
              </div>

              <div className="profile-info">
                <div className="info-item">
                  <User size={20} className="info-icon" />
                  <div className="info-content">
                    <label>Full Name</label>
                    <span>{name}</span>
                  </div>
                </div>

                <div className="info-item">
                  <Mail size={20} className="info-icon" />
                  <div className="info-content">
                    <label>Email Address</label>
                    <span>{email}</span>
                  </div>
                </div>
              </div>

              <div className="profile-footer">
                <button className="logout-action-btn" onClick={handleLogout}>
                  <LogOut size={18} /> Logout from Session
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
