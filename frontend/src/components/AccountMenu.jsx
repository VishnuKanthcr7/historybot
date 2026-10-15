import { Link } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";

export default function AccountMenu({ variant = "chat", teacherLabel = "Teacher Login" }) {
  const { user, logout } = useApp();
  const home = variant === "home";
  const className = home
    ? "home-account"
    : "inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-full border border-rule bg-cream px-3 text-sm text-navy";

  if (!user) {
    if (!home) {
      return (
        <Link to="/login" className={className}>
          Student login
        </Link>
      );
    }
    return (
      <>
        <Link to="/login" className={className}>
          Student Login
        </Link>
        <Link to="/signup" className={className}>
          Student Sign Up
        </Link>
        <Link to="/teacher/login" className={className}>
          {teacherLabel}
        </Link>
      </>
    );
  }

  return (
    <>
      <Link to="/quizzes" className={className}>
        Quizzes
      </Link>
      {home ? (
        <Link to="/activities" className={className}>
          Activities
        </Link>
      ) : null}
      {user.role === "admin" ? (
        <Link to="/admin" className={className}>
          Dashboard
        </Link>
      ) : null}
      <button type="button" className={className} onClick={() => logout()}>
        Log out
      </button>
    </>
  );
}
