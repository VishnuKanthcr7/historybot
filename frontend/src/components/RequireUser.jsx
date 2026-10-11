import { Navigate, Outlet } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";

export default function RequireUser() {
  const { ready, user } = useApp();
  if (!ready) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}