import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../services/authService";

export default function LoginPage() {
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const data = await login(form);
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("name", data.name);
      localStorage.setItem("email", form.email);
      navigate("/chat");
    } catch (err) {
      setError(err?.response?.data?.detail || "Login failed");
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-brand">
        <h1>Safar AI</h1>
      </div>
      <div className="auth-layout">
        <h2>Login</h2>
        <form onSubmit={onSubmit} className="auth-form">
          <input
            type="email"
            placeholder="Email"
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
          <input
            type="password"
            placeholder="Password"
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
          <button type="submit">Login</button>
        </form>
        {error && <p className="error">{error}</p>}
        <p>
          New user? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  );
}
