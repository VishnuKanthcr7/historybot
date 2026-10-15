// "What counts?" text for the teacher dashboard. Each entry states exactly what the SQL in
// analyticsController.overviewData() counts (checked 15 Oct 2026). Change both together.
export const DEFINITIONS = {
  students_total: "Accounts with the student role that exist now, whatever their activity. Teacher accounts are not counted.",
  registered_in_range:
    "Accounts with the student role created in the date range (IST). Teacher accounts are not counted; deleted accounts no longer appear.",
  active_students:
    "Students who, in the date range, asked at least one chat question, opened a learning module, finished a quiz or activity (submitted or timed out), or submitted a questionnaire. Signing in alone does not count. Not attendance.",
  sign_ins: "Successful sign-ins in the date range (recorded since progress tracking began). A sign-in is not attendance.",
  chat_questions: "Questions students typed in chat in the date range (count only; chat text is never shown).",
  modules_generated: "Learning modules students generated in the date range.",
  modules_opened: "Distinct student-module pairs first opened in the date range (refreshing does not count again).",
  modules_completed:
    "Distinct student-module pairs first completed in the date range: the student clicked 'Mark complete' or submitted the module's checkpoint quiz. Each module counts once per student; opening or downloading is not completion.",
  pdf_downloads: "Module PDF downloads by students in the date range (each download counts).",
  quiz_attempts: "Quiz and activity attempts finished (submitted or timed out) in the date range. Every attempt counts, including retries.",
  timed_out:
    "Attempts on any quiz or activity that the timer closed in the date range (scored from the last autosave). They are also counted in the finished attempts.",
  abandoned: "Untimed attempts still in progress more than 24 hours after they started (started in the date range).",
  assessments_submitted:
    "Finished attempts (submitted or timed out) in the date range on teacher quizzes in assessment mode, including pre/post tests. Every attempt counts. Practice quizzes and personal revision quizzes are not included.",
  mean_percent:
    "Assessment average: mean percent of each student's FIRST finished attempt (submitted or timed out) on each teacher quiz in assessment mode, including pre/post tests; it counts only when that first attempt was finished in the date range. Practice quizzes and personal revision quizzes are excluded; a timed-out attempt with no saved answers scores 0%.",
  practice_mean_percent:
    "Practice average: mean percent of ALL finished attempts in the date range on teacher quizzes and activities in practice mode, plus students' personal revision quizzes (every attempt counts, including retries). Assessment-mode quizzes are excluded.",
};

// Headline card labels (kept next to the definitions so they cannot drift apart).
export const HEADLINE_LABELS = {
  registered_in_range: "Students registered",
  active_students: "Active students",
  modules_completed: "Modules completed",
  assessments_submitted: "Assessment attempts",
  mean_percent: "Assessment average",
  practice_mean_percent: "Practice average",
};
