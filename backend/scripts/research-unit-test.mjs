// Unit tests (no database, no network): questionnaire scoring, publishing rules, paired t, PDF file names, IST stamps.
process.env.MYSQL_USER ||= "unit";
process.env.MYSQL_PASSWORD ||= "unit";
process.env.INTERNAL_RAG_SECRET ||= "unit-secret-unit-secret";
process.env.JWT_SECRET ||= "unit-jwt-secret-unit-jwt-secret-unit-jwt-secret";
process.env.SESSION_SECRET ||= "unit-session-secret-unit-session-secret";
const { scoreQuestionnaire, publishProblem, reverse, PLACEHOLDER_TAG } = await import("../src/services/questionnaireScoring.js");
const { pairedT, tTwoSidedP } = await import("../src/services/stats.js");
const { pdfFileNames } = await import("../src/controllers/econtentController.js");
const { istStamp } = await import("../src/controllers/analyticsController.js");
const { csvCell } = await import("../src/services/csv.js");

let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  ok ? pass++ : fail++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail !== "" ? ` — ${JSON.stringify(detail)}` : ""}`);
};

const items = [
  { id: "1", subscale: "X", reverse_scored: false },
  { id: "2", subscale: "X", reverse_scored: true },
  { id: "3", subscale: "Y", reverse_scored: false },
  { id: "4", subscale: "Y", reverse_scored: false },
];
const scale = { scaleMin: 1, scaleMax: 5, minRatio: 0.5 };
const s1 = scoreQuestionnaire(items, { 1: 5, 2: 1, 3: 4, 4: null }, scale);
check("reverse-scored item flips (1 -> 5 on a 1-5 scale)", reverse(1, 1, 5) === 5 && reverse(2, 0, 4) === 2);
check("subscale mean uses answered items after reversing", s1.subscales.find((s) => s.subscale === "X").score === 5);
check("half answered meets the 50% rule", s1.subscales.find((s) => s.subscale === "Y").score === 4);
check("missing is counted as missing, not zero", s1.answered === 3 && s1.missing === 1 && s1.completion === 0.75);
const s2 = scoreQuestionnaire(items, { 1: 3, 2: 3 }, scale);
check("no answers in a subscale -> null (insufficient), not 0", s2.subscales.find((s) => s.subscale === "Y").score === null);
const s3 = scoreQuestionnaire(items, { 1: 0, 2: 6, 3: 2.5, 4: "4" }, scale);
check("out-of-range, fractional and string values are ignored", s3.answered === 0 && s3.subscales.every((s) => s.score === null));
const strict = scoreQuestionnaire(items, { 1: 4, 3: 4 }, { ...scale, minRatio: 0.75 });
check("stricter minimum ratio leaves half-answered subscales unscored", strict.subscales.every((s) => s.score === null));

const ok = { approval_note: "Approved by Dr R, items from source Z (2025).", phase: "none" };
check("publishing: no items blocked", publishProblem(ok, []) !== null);
check("publishing: placeholder text blocked", /REQUIRES RESEARCHER APPROVAL/.test(publishProblem(ok, [{ text: `${PLACEHOLDER_TAG} item`, requires_approval: false }]) || ""));
check("publishing: requires_approval flag blocked", publishProblem(ok, [{ text: "Real item", requires_approval: true }]) !== null);
check("publishing: approval note required", publishProblem({ ...ok, approval_note: "" }, [{ text: "Real item" }]) !== null);
check("publishing: post needs a linked pre", publishProblem({ ...ok, phase: "post", pre_instrument_id: null }, [{ text: "Real item" }]) !== null);
check("publishing: approved items pass", publishProblem(ok, [{ text: "Real item", requires_approval: false }]) === null);

check("t distribution: t=2.228, df=10 -> p 0.05", Math.abs(tTwoSidedP(2.228, 10) - 0.05) < 0.001);
const t = pairedT([50, 75]);
check("paired t on gains [50, 75] -> t 5, df 1, p 0.1257", t.t === 5 && t.df === 1 && Math.abs(t.p - 0.1257) < 0.0005, t);
check("paired t needs n >= 2", pairedT([10]).t === null);
check("identical gains -> t undefined (no fake p)", pairedT([10, 10]).t === null && pairedT([10, 10]).p === null);

const f1 = pdfFileNames("The Mughal Empire: Akbar's Reforms");
check("PDF file name is ASCII and safe", f1.ascii === "historybot-The-Mughal-Empire-Akbar-s-Reforms.pdf", f1);
const f2 = pdfFileNames("ಮೊಘಲ್ ಸಾಮ್ರಾಜ್ಯ");
check("Kannada title: ASCII fallback plus UTF-8 name", f2.ascii === "historybot-module.pdf" && decodeURIComponent(f2.utf8) === "historybot-ಮೊಘಲ್-ಸಾಮ್ರಾಜ್ಯ.pdf", f2);
check("PDF header value has only Latin-1 characters", /^[\x20-\x7e]*$/.test(`attachment; filename="${f2.ascii}"; filename*=UTF-8''${f2.utf8}`));

check("IST stamp: 18:30 UTC -> next day 00:00 IST", istStamp("2026-10-14T18:30:00Z") === "2026-10-15 00:00:00 IST");
check("IST stamp: empty stays empty", istStamp(null) === "");
check("CSV guard still neutralises formulas", csvCell("=SUM(A1)") === "'=SUM(A1)" && csvCell("-5") === "-5" && csvCell("@x") === "'@x");

console.log(`research_unit ${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
