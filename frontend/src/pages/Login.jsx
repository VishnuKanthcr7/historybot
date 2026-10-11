import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { clearPendingQuestion, pathAfterStudentAuth } from "../pendingQuestion.js";

export default function Login({ teacher = false, initialMode = "login" }) {
  const { user, ready, login, register } = useApp();
  const [mode, setMode] = useState(teacher ? "login" : initialMode);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (ready && user) {
    if (user.role === "admin") {
      clearPendingQuestion();
      return <Navigate to="/admin" replace />;
    }
    return <Navigate to={pathAfterStudentAuth()} replace />;
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (!teacher && mode === "register") {
        if (password !== confirmPassword) {
          setError("Password and confirm password do not match.");
          return;
        }
        await register(displayName, email, password);
      } else {
        await login(email, password);
      }
    } catch (err) {
      setError(
        err.code === "VALIDATION_ERROR"
          ? "Enter a valid email and a password of at least 8 characters."
          : err.message || "Sign-in failed."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="gate-page">
      <div className="gate-card">
        <Link to="/" className="gate-brand">
          HistoryBot
        </Link>
        <h1 className="sr-only">
          {teacher ? "Teacher login" : mode === "register" ? "Student sign up" : "Student login"}
        </h1>
        <p className="mt-2 text-sm text-muted">
          {teacher ? "Teacher / Admin sign-in" : "Class 9 Social Science · Karnataka State Board"}
        </p>
        {teacher ? null : (
          <div className="mt-6 grid grid-cols-2 gap-2">
            <button
              type="button"
              className={`min-h-11 rounded-full text-sm ${mode === "login" ? "bg-navy text-cream" : "border border-rule"}`}
              onClick={() => setMode("login")}
            >
              Student login
            </button>
            <button
              type="button"
              className={`min-h-11 rounded-full text-sm ${mode === "register" ? "bg-navy text-cream" : "border border-rule"}`}
              onClick={() => setMode("register")}
            >
              Student sign up
            </button>
          </div>
        )}
        <form className="mt-6 space-y-3" onSubmit={submit}>
          {!teacher && mode === "register" ? (
            <label className="block text-sm">
              Name
              <input
                className="gate-input"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
                required
              />
            </label>
          ) : null}
          <label className="block text-sm">
            Email
            <input
              className="gate-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="block text-sm">
            Password
            <input
              className="gate-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              minLength={!teacher && mode === "register" ? 8 : 1}
              required
            />
          </label>
          {!teacher && mode === "register" ? (
            <label className="block text-sm">
              Confirm password
              <input
                className="gate-input"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
          ) : null}
          {error ? (
            <p className="border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            className="min-h-11 w-full rounded-full bg-navy text-sm font-medium text-cream disabled:opacity-50"
            disabled={busy || !ready}
          >
            {busy ? "Please wait..." : !teacher && mode === "register" ? "Create student account" : "Log in"}
          </button>
        </form>
        <p className="gate-note">
          {teacher
            ? "Teacher accounts are created by the project administrator. There is no public teacher registration."
            : mode === "register"
              ? "Sign-up creates a student account only. It does not verify that you own this email address."
              : "Sign-up creates a student account only. Teachers use Teacher login."}
        </p>
        <p className="mt-3 text-sm">
          <Link to="/" className="text-navy">
            Back to welcome page
          </Link>
        </p>
      </div>
    </div>
  );
}
