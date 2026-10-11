const PENDING_KEY = "historybot_pending_question";

export function stashPendingQuestion(text) {
  const question = String(text || "").trim();
  if (question) sessionStorage.setItem(PENDING_KEY, question);
  else sessionStorage.removeItem(PENDING_KEY);
}

export function readPendingQuestion() {
  return (sessionStorage.getItem(PENDING_KEY) || "").trim();
}

export function clearPendingQuestion() {
  sessionStorage.removeItem(PENDING_KEY);
}

export function pathAfterStudentAuth() {
  const question = readPendingQuestion();
  if (!question) return "/chat?fresh=1";
  return `/chat?q=${encodeURIComponent(question)}`;
}
