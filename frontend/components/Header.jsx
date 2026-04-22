import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '../src/ThemeContext';

export default function Header() {
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const userName = localStorage.getItem("name") || "User";
  const userInitial = userName.charAt(0).toUpperCase();

  return (
    <header className="top-header">
      <div className="header-branding">
        <h2>SAFAR AI</h2>
      </div>
      
      <div className="header-actions">
        {/* Simple Toggle */}
        <div className={`theme-toggle ${theme}`} onClick={toggleTheme}>
          <div className="toggle-thumb"></div>
        </div>

        {/* Account Button */}
        <div className="account-section">
          <button 
            className="user-profile-btn" 
            title="Account Settings"
            onClick={() => navigate('/profile')}
          >
            {userInitial}
          </button>
        </div>
      </div>
    </header>
  );
}
