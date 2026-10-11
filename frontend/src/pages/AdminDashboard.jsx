import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { adminSummary } from "../services/api.js";

export default function AdminDashboard() {
  const { user, ready } = useApp();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ready || !user || user.role !== "admin") return;
    let cancelled = false;
    adminSummary()
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "The dashboard could not be opened.");
      });
    return () => {
      cancelled = true;
    };
  }, [ready, user]);

  if (!ready) {
    return <p className="p-8 text-sm text-muted">Loading...</p>;
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-paper px-4 py-10 font-sans text-ink">
      <div className="mx-auto max-w-2xl rounded-3xl border border-rule bg-cream p-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brass">Teacher</p>
        <h1 className="mt-1 font-serif text-3xl text-navy">Dashboard</h1>
        <p className="mt-3 text-sm">
          Signed in as <strong>{user.display_name}</strong>
        </p>
        <p className="mt-4 text-sm leading-relaxed">{summary?.note || error || "Loading dashboard..."}</p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Link to="/" className="min-h-11 rounded-full bg-navy px-4 py-2 text-sm text-cream">
            Homepage
          </Link>
          <Link to="/chat?fresh=1" className="min-h-11 rounded-full border border-navy px-4 py-2 text-sm text-navy">
            Start Learning
          </Link>
        </div>
      </div>
    </div>
  );
}
