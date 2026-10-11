export async function adminSummary(req, res) {
  res.json({
    user: req.user,
    title: "Teacher dashboard",
    note: "Chat, textbook answers, images, and learning-module PDFs are available from Start Learning. Further dashboard tools will be added after the client confirms them.",
  });
}
