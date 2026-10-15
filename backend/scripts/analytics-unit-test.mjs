// Deterministic unit tests (no DB, no network): IST day bucketing for the activity chart and seeded quiz randomisation.
import { buildSeries, enumerateBuckets, istDayKey } from "../src/services/timeseries.js";
import { applyOptionOrder, buildLayout, layoutOf, rng, shouldRandomize } from "../src/services/quizRandom.js";
import { gradeQuestion } from "../src/services/quizScoring.js";

let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  ok ? pass++ : fail++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};

// --- IST day keys around midnight
check("18:29:59Z is still the same IST day (23:59:59 IST)", istDayKey("2026-10-14T18:29:59.999Z") === "2026-10-14");
check("18:30:00Z is the next IST day (00:00 IST)", istDayKey("2026-10-14T18:30:00.000Z") === "2026-10-15");
check("00:00Z is 05:30 IST same date", istDayKey("2026-10-15T00:00:00Z") === "2026-10-15");

// --- enumerate
check("one-day range has exactly one bucket", JSON.stringify(enumerateBuckets("2026-10-15", "2026-10-15")) === '["2026-10-15"]');
check("inclusive 3-day range", enumerateBuckets("2026-10-13", "2026-10-15").length === 3);
check("month boundary", JSON.stringify(enumerateBuckets("2026-09-30", "2026-10-01")) === '["2026-09-30","2026-10-01"]');
check("weeks start on Monday", JSON.stringify(enumerateBuckets("2026-10-14", "2026-10-20", "week")) === '["2026-10-12","2026-10-19"]');

// --- empty range
const empty = buildSeries({}, "2026-10-01", "2026-10-07");
check("empty range: 7 zero days, flagged empty", empty.series.length === 7 && empty.empty && empty.totals.chat_questions === 0);

// --- one-day with multiple activity types
const one = buildSeries(
  {
    quiz: [{ bucket: "2026-10-15", n: 2, students: 1, mean_percent: "40.00" }],
    chat: [{ bucket: "2026-10-15", n: 5, students: 2 }],
    events: [
      { bucket: "2026-10-15", event_type: "MODULE_OPENED", n: 3 },
      { bucket: "2026-10-15", event_type: "MODULE_COMPLETED", n: 1 },
      { bucket: "2026-10-15", event_type: "PDF_DOWNLOADED", n: 4 },
      { bucket: "2026-10-15", event_type: "USER_SIGNED_IN", n: 6 },
      { bucket: "2026-10-15", event_type: "QUESTION_ASKED", n: 99 },
    ],
  },
  "2026-10-15",
  "2026-10-15"
);
const d = one.series[0];
check(
  "one day, all activity types counted; unknown types ignored",
  one.series.length === 1 && d.quiz_attempts === 2 && d.chat_questions === 5 && d.modules_opened === 3 && d.modules_completed === 1 && d.pdf_downloads === 4 && d.sign_ins === 6 && d.mean_percent === 40 && !one.empty,
  JSON.stringify(d)
);

// --- rows outside the range are dropped; zero days kept between active days
const gap = buildSeries({ chat: [{ bucket: "2026-10-10", n: 1 }, { bucket: "2026-10-12", n: 2 }, { bucket: "2026-10-20", n: 9 }] }, "2026-10-10", "2026-10-12");
check("zero day kept between active days; out-of-range row ignored", gap.series.map((p) => p.chat_questions).join(",") === "1,0,2" && gap.totals.chat_questions === 3);

// --- an event at 23:59 IST and one at 00:01 IST land on different days
const late = istDayKey("2026-10-14T18:29:00Z");
const early = istDayKey("2026-10-14T18:31:00Z");
const mid = buildSeries({ events: [{ bucket: late, event_type: "MODULE_OPENED", n: 1 }, { bucket: early, event_type: "MODULE_OPENED", n: 1 }] }, "2026-10-14", "2026-10-15");
check("events either side of IST midnight fall in separate days", mid.series.map((p) => p.modules_opened).join(",") === "1,1");

// --- seeded randomisation
const items = [
  { id: "q1", qtype: "mcq", options_json: JSON.stringify([{ id: "a", text: "A" }, { id: "b", text: "B" }, { id: "c", text: "C" }, { id: "d", text: "D" }]), answer_json: '"c"' },
  { id: "q2", qtype: "true_false", options_json: null, answer_json: "true" },
  { id: "q3", qtype: "match", options_json: JSON.stringify({ left: [{ id: "l1", text: "x" }, { id: "l2", text: "y" }], right: [{ id: "r1", text: "1" }, { id: "r2", text: "2" }] }) },
  { id: "q4", qtype: "order", options_json: JSON.stringify([{ id: "i1", text: "1" }, { id: "i2", text: "2" }, { id: "i3", text: "3" }]) },
  { id: "q5", qtype: "fill_blank", options_json: null },
];
const practice = { mode: "practice", assessment_phase: "none" };
const l1 = buildLayout(items, practice, "seed-1");
const l2 = buildLayout(items, practice, "seed-1");
check("same seed gives the same layout", JSON.stringify(l1) === JSON.stringify(l2));
const seen = new Set();
for (let i = 0; i < 40; i++) seen.add(buildLayout(items, practice, `seed-${i}`).order.join(","));
check("different seeds give different question orders", seen.size > 5, `distinct=${seen.size}`);
let perm = true;
for (let i = 0; i < 40; i++) {
  const l = buildLayout(items, practice, `s${i}`);
  if (l.order.length !== 5 || new Set(l.order).size !== 5 || !items.every((q) => l.order.includes(q.id))) perm = false;
  if ([...l.options.q1].sort().join("") !== "abcd") perm = false;
}
check("every attempt uses each pool question exactly once; options are a permutation", perm);
check("pre-test is not randomised", JSON.stringify(buildLayout(items, { mode: "assessment", assessment_phase: "pre" }, "x").order) === '["q1","q2","q3","q4","q5"]');
check("post-test is not randomised", !shouldRandomize({ assessment_phase: "post" }) && Object.keys(buildLayout(items, { assessment_phase: "post" }, "x").options).length === 0);

// answer mapping intact after shuffle: the correct option id still scores correct
const pub = { id: "q1", qtype: "mcq", options: JSON.parse(items[0].options_json) };
const shuffled = applyOptionOrder(pub, ["d", "c", "b", "a"]);
check("option order applied by id", shuffled.options.map((o) => o.id).join("") === "dcba" && shuffled.options[1].text === "C");
const sc = gradeQuestion({ ...items[0] }, "c");
check("scoring by option id is unaffected by display order", sc && (sc.correct === true || sc.points > 0), JSON.stringify(sc));

check("legacy array layout still readable", JSON.stringify(layoutOf({ question_order_json: '["q2","q1"]' }).order) === '["q2","q1"]');
const r = rng("abc");
check("PRNG is deterministic", r() === rng("abc")());

// --- fill-in-the-blank name variants (server-side grading)
const fb = (answer) => ({ qtype: "fill_blank", answer_json: JSON.stringify(answer) });
const ok = (answer, given) => gradeQuestion(fb(answer), given).correct;
check("full name accepted for a short answer (Babur)", ok(["babur"], "Zahir-ud-din Muhammad Babur") && ok(["babur"], "Zahiruddin Muhammad Babur") && ok(["babur"], "babar"));
check("short name accepted for a full-name answer", ok(["zahir ud din muhammad babur"], "Babur"));
check("spacing/hyphen variants accepted (Jija Bai, Din-i-Ilahi, Sukapha)", ok(["jijabai"], "Jija Bai") && ok(["din-e-ilahi"], "Din i Ilahi") && ok(["din-e-ilahi"], "DinEIlahi") && ok(["sukaphaa"], "Sukapha"));
check("a different person is still wrong (Humayun for Babur, Akbar for Shivaji's mother)", !ok(["babur"], "Humayun") && !ok(["jijabai"], "Akbar") && !ok(["babur"], "Muhammad"));
check("partial or empty answers are wrong", !ok(["babur"], "") && !ok(["babur"], "bab") && !ok(["turkish"], "persian") && !ok(["sukaphaa"], "Ahom"));

console.log(`analytics_unit ${pass}/${pass + fail} ${fail ? "FAIL" : "PASS"}`);
process.exit(fail ? 1 : 0);
