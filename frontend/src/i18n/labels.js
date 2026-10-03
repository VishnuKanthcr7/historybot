export const LABELS = {
  en: {
    brand: "HistoryBot",
    tagline: "AI-Powered History Learning Assistant",
    start: "Start Learning",
    askPlaceholderHome: "Ask something about your History textbook...",
    newChat: "New Chat",
    history: "History",
    ask: "Ask a question",
    sources: "Sources",
    source: "Source",
    send: "Send",
    thinking: "Thinking from your textbook...",
    emptyChat: "Ask a question from the Class 9 History textbook.",
    language: "Language",
    english: "English",
    kannada: "ಕನ್ನಡ",
    textbookSource: "Textbook source",
    textbookPage: "Textbook page",
    textbookPages: "Textbook pages",
    openMenu: "Open chat history",
    closeMenu: "Close chat history",
    composerLabel: "Your question",
  },
  kn: {
    brand: "HistoryBot",
    tagline: "ಐತಿಹಾಸಿಕ ಪಠ್ಯಪುಸ್ತಕ ಆಧಾರಿತ ಕಲಿಕಾ ಸಹಾಯಕ",
    start: "ಕಲಿಕೆ ಪ್ರಾರಂಭಿಸಿ",
    askPlaceholderHome: "ನಿಮ್ಮ ಇತಿಹಾಸ ಪಠ್ಯಪುಸ್ತಕದ ಬಗ್ಗೆ ಕೇಳಿ...",
    newChat: "ಹೊಸ ಚಾಟ್",
    history: "ಇತಿಹಾಸ",
    ask: "ಪ್ರಶ್ನೆಯನ್ನು ಕೇಳಿ",
    sources: "ಮೂಲಗಳು",
    source: "ಮೂಲ",
    send: "ಕಳುಹಿಸಿ",
    thinking: "ಪಠ್ಯಪುಸ್ತಕದಿಂದ ಉತ್ತರಿಸಲಾಗುತ್ತಿದೆ...",
    emptyChat: "9ನೇ ತರಗತಿ ಇತಿಹಾಸ ಪಠ್ಯಪುಸ್ತಕದಿಂದ ಪ್ರಶ್ನೆ ಕೇಳಿ.",
    language: "ಭಾಷೆ",
    english: "English",
    kannada: "ಕನ್ನಡ",
    textbookSource: "ಪಠ್ಯಪುಸ್ತಕದ ಮೂಲ",
    textbookPage: "ಪಠ್ಯಪುಸ್ತಕ ಪುಟ",
    textbookPages: "ಪಠ್ಯಪುಸ್ತಕ ಪುಟಗಳು",
    openMenu: "ಚಾಟ್ ಇತಿಹಾಸ ತೆರೆಯಿರಿ",
    closeMenu: "ಚಾಟ್ ಇತಿಹಾಸ ಮುಚ್ಚಿರಿ",
    composerLabel: "ನಿಮ್ಮ ಪ್ರಶ್ನೆ",
  },
};

export function formatSourcePages(sources, language = "en") {
  const pages = [
    ...new Set(
      (sources || [])
        .map((item) => Number(item.textbook_page_number))
        .filter((n) => Number.isFinite(n))
    ),
  ].sort((a, b) => a - b);
  const t = LABELS[language] || LABELS.en;
  if (!pages.length) return "";
  const joiner = language === "kn" ? " ಮತ್ತು " : " and ";
  if (pages.length === 1) return `${t.textbookPage} ${pages[0]}`;
  if (pages.length === 2) return `${t.textbookPages} ${pages[0]}${joiner}${pages[1]}`;
  const head = pages.slice(0, -1).join(", ");
  return `${t.textbookPages} ${head}${joiner}${pages[pages.length - 1]}`;
}
