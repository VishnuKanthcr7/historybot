import { Navigate, Route, Routes } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Chat from "./pages/Chat.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
