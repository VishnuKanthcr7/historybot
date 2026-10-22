import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { clearPendingQuestion, pathAfterStudentAuth } from "../pendingQuestion.js";

const ROLL_RE = /^(0[1-9]|[1-9][0-9])$/;

// Simple messages for Class 9 students. Returns "" when the form is fine.
export function checkStudentForm({ mode, displayName, roll, password, confirmPassword }) {
  if (mode === "register" && displayName.trim().replace(/\s+/g, " ").length < 2) return "Please type your full name.";
  if (!/^\d{2}$/.test(roll)) return "Roll number must be two digits. Example: 07 (not 7).";
  if (!ROLL_RE.test(roll)) return "Roll number must be from 01 to 99.";
  if (mode === "register") {
    if (password.length < 8) return "Password must have at least 8 characters.";
    if (password !== confirmPassword) return "The two passwords are not the same. Please type them again.";
  } else if (!password) {
    return "Please type your password.";
  }
  return "";
}

export default function Login({ teacher = false, initialMode = "login" }) {
  const { user, ready, login, register } = useApp();
  const [mode, setMode] = useState(teacher ? "login" : initialMode);
  // Students who signed up with an email before roll numbers were introduced can still use it.
  const [useEmail, setUseEmail] = useState(teacher);
  const [displayName, setDisplayName] = useState("");
  const [roll, setRoll] = useState("");
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

  const registering = !teacher && mode === "register";
  const byEmail = teacher || (useEmail && !registering);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!byEmail) {
      const problem = checkStudentForm({ mode: registering ? "register" : "login", displayName, roll, password, confirmPassword });
      if (problem) {
        setError(problem);
        return;
      }
    }
    setBusy(true);
    try {
      if (registering) {
        await register(displayName.trim().replace(/\s+/g, " "), roll, password, confirmPassword);
      } else if (byEmail) {
        await login({ email }, password);
      } else {
        await login({ roll_number: roll }, password);
      }
    } catch (err) {
      setError(
        err.code === "VALIDATION_ERROR"
          ? err.message && !/invalid request/i.test(err.message)
            ? err.message
            : byEmail
              ? "Enter a valid email and your password."
              : "Please check your roll number and password."
          : err.message || "Sign-in failed."
      );
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next) {
    setMode(next);
    setError("");
    if (next === "register") setUseEmail(false);
  }

  return (
    <div className="gate-page">
      <div className="gate-card">
        <Link to="/" className="gate-brand">
          HistoryBot
        </Link>
        <h1 className="sr-only">{teacher ? "Teacher login" : registering ? "Student sign up" : "Student login"}</h1>
        <p className="mt-2 text-sm text-muted">
          {teacher ? "Teacher / Admin sign-in" : "Class 9 Social Science · Karnataka State Board"}
        </p>
        {teacher ? null : (
          <div className="mt-6 grid grid-cols-2 gap-2">
            <button
              type="button"
              className={`min-h-11 rounded-full text-sm ${mode === "login" ? "bg-navy text-cream" : "border border-rule"}`}
              onClick={() => switchMode("login")}
            >
              Student login
            </button>
            <button
              type="button"
              className={`min-h-11 rounded-full text-sm ${mode === "register" ? "bg-navy text-cream" : "border border-rule"}`}
              onClick={() => switchMode("register")}
            >
              Student sign up
            </button>
          </div>
        )}
        <form className="mt-6 space-y-3" onSubmit={submit} noValidate>
          {registering ? (
            <label className="block text-sm">
              Full name
              <input
                className="gate-input"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
                maxLength={80}
                required
              />
            </label>
          ) : null}
          {byEmail ? (
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
          ) : (
            <label className="block text-sm">
              Roll number (two digits, for example 07)
              <input
                className="gate-input"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{2}"
                maxLength={2}
                value={roll}
                onChange={(e) => setRoll(e.target.value.replace(/\D/g, "").slice(0, 2))}
                autoComplete="username"
                required
              />
            </label>
          )}
          <label className="block text-sm">
            Password
            <input
              className="gate-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={registering ? "new-password" : "current-password"}
              required
            />
          </label>
          {registering ? (
            <label className="block text-sm">
              Confirm password
              <input
                className="gate-input"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
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
            {busy ? "Please wait..." : registering ? "Create student account" : "Log in"}
          </button>
        </form>
        {!teacher && !registering ? (
          <p className="mt-3 text-sm">
            <button type="button" className="min-h-11 text-left text-navy underline" onClick={() => { setUseEmail(!useEmail); setError(""); }}>
              {useEmail ? "Use my roll number instead" : "Signed up earlier with an email? Use email instead"}
            </button>
          </p>
        ) : null}
        <p className="gate-note">
          {teacher
            ? "Teacher accounts are created by the project administrator. There is no public teacher registration."
            : registering
              ? "No email or phone number is needed. Remember your roll number and password. Password at least 8 characters."
              : "Students log in with their roll number and password. Teachers use Teacher login."}
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
