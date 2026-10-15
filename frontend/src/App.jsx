import { Navigate, Route, Routes } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Chat from "./pages/Chat.jsx";
import Login from "./pages/Login.jsx";
import Start from "./pages/Start.jsx";
import AdminDashboard from "./pages/AdminDashboard.jsx";
import RequireUser from "./components/RequireUser.jsx";
import Quizzes from "./pages/Quizzes.jsx";
import QuizPlayer from "./pages/QuizPlayer.jsx";
import Activities from "./pages/Activities.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/start" element={<Start />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Login initialMode="register" />} />
      <Route path="/teacher/login" element={<Login teacher />} />
      <Route element={<RequireUser />}>
        <Route path="/chat" element={<Chat />} />
        <Route path="/quizzes" element={<Quizzes />} />
        <Route path="/activities" element={<Activities />} />
        <Route path="/attempts/:attemptId" element={<QuizPlayer />} />
      </Route>
      <Route path="/admin" element={<AdminDashboard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
