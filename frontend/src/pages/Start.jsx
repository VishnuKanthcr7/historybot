import { Link, Navigate } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { pathAfterStudentAuth } from "../pendingQuestion.js";

export default function Start() {
  const { user, ready } = useApp();

  if (!ready) {
    return <p className="px-4 py-10 text-sm text-muted">Loading...</p>;
  }
  if (user?.role === "admin") return <Navigate to="/admin" replace />;
  if (user) return <Navigate to={pathAfterStudentAuth()} replace />;

  return (
    <div className="gate-page">
      <div className="gate-card">
        <Link to="/" className="gate-brand">
          HistoryBot
        </Link>
        <h1>Continue to learning</h1>
        <p>
          Sign in before asking a question. Chat, textbook citations, images, and learning modules
          stay available after you sign in.
        </p>
        <div className="gate-actions">
          <Link to="/signup" className="gate-primary">
            Create Student Account
          </Link>
          <Link to="/login" className="gate-secondary">
            Already have an account? Student Login
          </Link>
          <Link to="/teacher/login" className="gate-secondary">
            Teacher Login
          </Link>
        </div>
        <p className="gate-note">
          Public registration creates a student account. Teacher accounts are created separately by
          the project administrator.
        </p>
      </div>
    </div>
  );
}
