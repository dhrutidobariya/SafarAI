import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "../services/authService";

export default function RegisterPage() {
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const data = await register(form);
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("name", data.name);
      localStorage.setItem("email", form.email);
      navigate("/chat");
    } catch (err) {
      setError(err?.response?.data?.detail || "Registration failed");
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-brand">
        <h1>Safar AI</h1>
      </div>
      <div className="auth-layout">
        <h2>Register</h2>
        <form onSubmit={onSubmit} className="auth-form">
          <input
            placeholder="Name"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
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
          <button type="submit">Create Account</button>
        </form>
        {error && <p className="error">{error}</p>}
        <p>
          Already registered? <Link to="/login">Login</Link>
        </p>
      </div>
    </div>
  );
}
