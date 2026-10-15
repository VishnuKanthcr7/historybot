// Pure unit tests: scoring, response sanitising, reveal rules, CSV guard, draft generation, question validation.
const { gradeQuestion, scoreAttempt, sanitizeResponses, studentQuestion, median, mean } = await import("../src/services/quizScoring.js");
const { csvCell, toCsv } = await import("../src/services/csv.js");
const { revealAllowed, quizIsOpen } = await import("../src/services/quizData.js");
const { questionProblem, draftFromSentence, splitSentences } = await import("../src/controllers/teacherQuizController.js");

let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  if (ok) pass += 1;
  else fail += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail !== "" ? ` — ${detail}` : ""}`);
};

const mcq = { id: "q1", qtype: "mcq", options_json: JSON.stringify([{ id: "a", text: "A" }, { id: "b", text: "B" }]), answer_json: JSON.stringify("b") };
const tf = { id: "q2", qtype: "true_false", answer_json: "false" };
const fill = { id: "q3", qtype: "fill_blank", answer_json: JSON.stringify(["din-e-ilahi", "din i ilahi"]) };
const order = { id: "q4", qtype: "order", options_json: "[]", answer_json: JSON.stringify(["i1", "i2", "i3"]) };
const match = { id: "q5", qtype: "match", answer_json: JSON.stringify({ l1: "r1", l2: "r2", l3: "r3", l4: "r4" }) };

check("mcq with mysql2-decoded JSON (plain string key)", gradeQuestion({ qtype: "mcq", options_json: [{ id: "a" }, { id: "b" }], answer_json: "b" }, "b").correct === true);
check("fill blank with decoded array key", gradeQuestion({ qtype: "fill_blank", answer_json: ["jijabai"] }, "Jijabai").correct === true);
check("mcq correct", gradeQuestion(mcq, "b").correct === true);
check("mcq incorrect", gradeQuestion(mcq, "a").fraction === 0);
check("mcq invalid option id scores 0", gradeQuestion(mcq, "z").fraction === 0);
check("mcq empty scores 0", gradeQuestion(mcq, null).fraction === 0 && gradeQuestion(mcq, "").fraction === 0);
check("true/false correct (false)", gradeQuestion(tf, false).correct === true);
check("true/false string 'false' is invalid", gradeQuestion(tf, "false").fraction === 0);
check("fill blank tolerant to case/punctuation", gradeQuestion(fill, "  Din-E-Ilahi ").correct && gradeQuestion(fill, "Din i Ilahi.").correct);
check("fill blank wrong", !gradeQuestion(fill, "Ibadat Khana").correct);
check("fill blank empty", gradeQuestion(fill, "").fraction === 0);
check("order exact", gradeQuestion(order, ["i1", "i2", "i3"]).correct);
check("order wrong is 0 (all or nothing)", gradeQuestion(order, ["i2", "i1", "i3"]).fraction === 0);
check("order wrong length", gradeQuestion(order, ["i1", "i2"]).fraction === 0);
check("match partial credit", gradeQuestion(match, { l1: "r1", l2: "r2", l3: "r4", l4: "r3" }).fraction === 0.5);
check("match full", gradeQuestion(match, { l1: "r1", l2: "r2", l3: "r3", l4: "r4" }).correct);
check("match reusing one answer earns no extra credit", gradeQuestion(match, { l1: "r1", l2: "r1", l3: "r1", l4: "r1" }).fraction === 0.25);
check("match non-object is 0", gradeQuestion(match, ["r1"]).fraction === 0);

const items = [mcq, tf, fill, order, match].map((q) => ({ question: q, points: 1 }));
let r = scoreAttempt(items, { q1: "b", q2: false, q3: "din-e-ilahi", q4: ["i1", "i2", "i3"], q5: { l1: "r1", l2: "r2", l3: "r3", l4: "r4" } });
check("all correct = 100%", r.percent === 100 && r.score === 5 && r.max === 5, JSON.stringify([r.score, r.max, r.percent]));
r = scoreAttempt(items, {});
check("empty submission = 0%", r.percent === 0 && r.answers.every((a) => a.points === 0));
r = scoreAttempt(items, { q1: "b", q5: { l1: "r1", l2: "r2", l3: "r4", l4: "r3" } });
check("percent with partial match = 30%", r.percent === 30, r.percent);
r = scoreAttempt(items, "garbage");
check("non-object responses = 0%", r.percent === 0);
const clean = sanitizeResponses({ q1: "b", evil: "x", q4: ["i1", 5], q5: { l1: "r1" }, q2: false }, ["q1", "q2", "q4", "q5"]);
check("sanitize drops unknown question ids", !("evil" in clean) && clean.q1 === "b" && clean.q2 === false);
check("sanitize coerces array items to strings", Array.isArray(clean.q4) && clean.q4[1] === "5");
const sq = studentQuestion({ ...mcq, prompt: "P", explanation: "secret", topic: "T" });
check("student view has no answer or explanation", !("answer" in sq) && !("answer_json" in sq) && !("explanation" in sq));

const now = new Date();
check("practice reveals after submit", revealAllowed({ mode: "practice", reveal_answers: "after_submit", status: "published" }));
check("assessment after_close hidden while open", !revealAllowed({ mode: "assessment", reveal_answers: "after_close", status: "published" }));
check("assessment after_close shown when archived", revealAllowed({ mode: "assessment", reveal_answers: "after_close", status: "archived" }));
check("assessment after_close shown after available_until", revealAllowed({ mode: "assessment", reveal_answers: "after_close", status: "published", available_until: new Date(now - 1000) }));
check("assessment never hidden", !revealAllowed({ mode: "assessment", reveal_answers: "never", status: "archived" }));
check("quiz not open before available_from", !quizIsOpen({ status: "published", available_from: new Date(now.getTime() + 60000) }));
check("draft quiz not open", !quizIsOpen({ status: "draft" }));

check("csv guard =", csvCell("=HYPERLINK(\"x\")").startsWith("\"'=") || csvCell("=1+1") === "'=1+1", csvCell("=1+1"));
check("csv guard + - @", csvCell("+1") === "'+1" && csvCell("@SUM(A1)") === "'@SUM(A1)" && csvCell("-cmd") === "'-cmd");
check("csv keeps negative numbers", csvCell(-5) === "-5" && csvCell("-2.5") === "-2.5");
check("csv quotes commas/quotes/newlines", csvCell('a,"b"\nc') === '"a,""b""\nc"');
check("csv tab/CR start guarded", csvCell("\tx").startsWith("'") || csvCell("\tx").startsWith("\"'"));
check("toCsv header + rows", toCsv(["a", "b"], [[1, "=x"]]) === "a,b\r\n1,'=x\r\n");

check("validate mcq answer must be an option", questionProblem({ qtype: "mcq", options: [{ id: "a", text: "x" }, { id: "b", text: "y" }], answer: "c" }) !== "");
check("validate good mcq", questionProblem({ qtype: "mcq", options: [{ id: "a", text: "x" }, { id: "b", text: "y" }], answer: "a" }) === "");
check("validate fill blank needs ______", questionProblem({ qtype: "fill_blank", prompt: "No blank here", answer: ["x"] }) !== "");
check("validate match pairs once", questionProblem({ qtype: "match", options: { left: [{ id: "l1" }, { id: "l2" }], right: [{ id: "r1" }, { id: "r2" }] }, answer: { l1: "r1", l2: "r1" } }) !== "");
check("validate order ids", questionProblem({ qtype: "order", options: [{ id: "i1" }, { id: "i2" }], answer: ["i2", "i1"] }) === "");
const d = draftFromSentence("He established a new religious order named Din-e-Ilahi in 1582.", "fill_blank");
check("draft blanks the year", d && d.prompt.includes("______") && d.answer[0] === "1582", d && d.prompt);
const d2 = draftFromSentence("Shivaji was born in Shivneri of Pune district.", "fill_blank");
check("draft blanks a key name", d2 && d2.answer[0] === "Pune" || (d2 && d2.answer[0] === "Shivneri"), d2 && d2.answer[0]);
check("sentences split", splitSentences("Akbar was born in Amarkot in Sindh province. Humayun was his father and he ruled.").length === 2);
check("median/mean", median([1, 3, 2]) === 2 && median([1, 2, 3, 4]) === 2.5 && mean([2, 4]) === 3 && median([]) === null);

console.log(`quiz_unit ${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
