// Audits every question in the bank against the indexed textbook passages (data/quiz/textbook_passages.json).
// Flags unsupported, ambiguous or duplicate items. With --apply: DRAFT items with problems become 'needs_review'
// (with the reason in review_note) and a small set of wording fixes is applied. Nothing is ever published.
// Usage: node backend/scripts/audit-question-bank.mjs [--apply] [--report docs/question-bank-audit.md]
import fs from "node:fs";
import path from "node:path";
import { mysql, mysqlConfig, root } from "./lib/migrate-utils.mjs";

const norm = (t) =>
  String(t ?? "")
    .toLowerCase()
    .replace(/[\u2018\u2019\u201c\u201d'"`]/g, "")
    .replace(/[\u2013\u2014]/g, "-")
    .replace(/[^a-z0-9\-\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const parse = (v, f = null) => {
  if (v == null) return f;
  if (typeof v !== "string") return v;
  try {
    return JSON.parse(v);
  } catch {
    return v;
  }
};

// Wording fixes (only applied when the stored text still matches "from").
const FIXES = {
  "babur-language": { prompt: ["Babar wrote his autobiography in the ______ language.", "Babur wrote his autobiography in the ______ language."] },
  "akbar-dagh": { option: ["b", "dagh-mahali", "Dagh-mahali"] },
};

export function auditQuestions(questions, passages) {
  const passageText = new Map(passages.map((p) => [p.chunk_id, norm(p.text)]));
  const seed = new Map(
    JSON.parse(fs.readFileSync(path.join(root, "data/quiz/seed_questions.json"), "utf8")).map((q) => [q.key, q])
  );
  const seenPrompt = new Map();
  const results = [];
  for (const q of questions) {
    const problems = [];
    const label = q.seed_key || q.id;
    const options = parse(q.options_json);
    const answer = parse(q.answer_json);
    const sources = seed.get(q.seed_key)?.extra_sources || (q.source_chunk_id ? [{ chunk_id: q.source_chunk_id, excerpt: q.source_excerpt }] : []);
    if (!sources.length || sources.some((s) => !s.excerpt)) problems.push("unsupported: no textbook source excerpt recorded");
    const excerpts = [];
    for (const s of sources) {
      const passage = passageText.get(s.chunk_id);
      if (!passage) problems.push(`unsupported: cited passage ${s.chunk_id || "(none)"} is not in the indexed textbook`);
      else if (s.excerpt && !passage.includes(norm(s.excerpt))) problems.push(`unsupported: excerpt not found verbatim in ${s.chunk_id}`);
      excerpts.push(norm(s.excerpt));
    }
    const ex = excerpts.join(" | ");
    if (q.qtype === "mcq" && Array.isArray(options)) {
      const correct = options.find((o) => o.id === answer);
      if (!correct) problems.push("broken: the answer key is not one of the options");
      else if (ex && !ex.includes(norm(correct.text))) problems.push(`check: the correct option "${correct.text}" is not stated in the excerpt`);
      const texts = options.map((o) => norm(o.text));
      if (new Set(texts).size !== texts.length) problems.push("ambiguous: two options have the same text");
      for (const o of options) {
        if (o.id !== answer && norm(o.text).length > 2 && ex.includes(norm(o.text))) {
          problems.push(`check: distractor "${o.text}" also appears in the excerpt; confirm the prompt rules it out`);
        }
      }
    }
    if (q.qtype === "fill_blank") {
      if (!/_{3,}/.test(q.prompt)) problems.push("ambiguous: fill-in-the-blank prompt has no blank (______)");
      const accepted = (Array.isArray(answer) ? answer : [answer]).map(norm);
      if (ex && !accepted.some((a) => ex.includes(a))) problems.push("check: no accepted answer appears in the excerpt");
    }
    if (q.qtype === "true_false" && typeof answer !== "boolean") problems.push("broken: true/false key is not true or false");
    const key = norm(q.prompt);
    if (seenPrompt.has(key)) problems.push(`duplicate: same prompt as ${seenPrompt.get(key)}`);
    else seenPrompt.set(key, label);
    results.push({ id: q.id, key: label, status: q.status, qtype: q.qtype, topic: q.topic, page: q.textbook_page, prompt: q.prompt, problems });
  }
  return results;
}

async function main() {
  const apply = process.argv.includes("--apply");
  const reportIdx = process.argv.indexOf("--report");
  const reportPath = reportIdx > 0 ? process.argv[reportIdx + 1] : null;
  const passages = JSON.parse(fs.readFileSync(path.join(root, "data/quiz/textbook_passages.json"), "utf8"));
  const conn = await mysql.createConnection(mysqlConfig());
  try {
    let fixed = 0;
    if (apply) {
      for (const [seedKey, fix] of Object.entries(FIXES)) {
        const [rows] = await conn.query("SELECT id, prompt, options_json FROM quiz_questions WHERE seed_key = ?", [seedKey]);
        if (!rows.length) continue;
        if (fix.prompt && rows[0].prompt === fix.prompt[0]) {
          await conn.query("UPDATE quiz_questions SET prompt = ?, updated_at = UTC_TIMESTAMP(3) WHERE id = ?", [fix.prompt[1], rows[0].id]);
          fixed += 1;
        }
        if (fix.option) {
          const opts = parse(rows[0].options_json, []);
          const o = opts.find((x) => x.id === fix.option[0] && x.text === fix.option[1]);
          if (o) {
            o.text = fix.option[2];
            await conn.query("UPDATE quiz_questions SET options_json = ?, updated_at = UTC_TIMESTAMP(3) WHERE id = ?", [JSON.stringify(opts), rows[0].id]);
            fixed += 1;
          }
        }
      }
    }
    const [questions] = await conn.query("SELECT * FROM quiz_questions ORDER BY status, topic, created_at");
    const results = auditQuestions(questions, passages);
    let flagged = 0;
    const today = new Date(Date.now() + 330 * 60000).toISOString().slice(0, 10);
    for (const r of results) {
      const serious = r.problems.filter((p) => !p.startsWith("check:"));
      if (apply && serious.length && r.status === "draft") {
        await conn.query(
          "UPDATE quiz_questions SET status = 'needs_review', review_note = ?, updated_at = UTC_TIMESTAMP(3) WHERE id = ? AND status = 'draft'",
          [`Audit ${today}: ${serious.join("; ")}`.slice(0, 500), r.id]
        );
        r.status = "needs_review";
        flagged += 1;
      }
    }
    const counts = results.reduce((m, r) => ((m[r.status] = (m[r.status] || 0) + 1), m), {});
    const withProblems = results.filter((r) => r.problems.length);
    console.log(`AUDIT questions=${results.length} by_status=${JSON.stringify(counts)} with_findings=${withProblems.length} flagged_needs_review=${flagged} wording_fixes=${fixed}`);
    for (const r of withProblems) console.log(`  [${r.status}] ${r.key}: ${r.problems.join("; ")}`);
    if (reportPath) {
      const lines = [
        "# Question bank audit",
        "",
        `Run: ${today} (IST). Source of truth: indexed textbook passages in data/quiz/textbook_passages.json (Chapter 17).`,
        "Checks: cited excerpt found verbatim in the cited passage; MCQ key stated in the excerpt; distractors not also in the excerpt; duplicate options/prompts; blank present in fill-in items.",
        "Drafts with problems are set to needs_review. Nothing is published by the audit. 'check:' findings are advisory (the teacher should look).",
        "",
        `Totals: ${results.length} questions; ${JSON.stringify(counts)}; ${withProblems.length} with findings; ${flagged} set to needs_review; ${fixed} wording fixes.`,
        "",
        "| Status | Question | Type | Page | Findings |",
        "|---|---|---|---|---|",
        ...results.map((r) => `| ${r.status} | ${r.key} | ${r.qtype} | ${r.page ?? ""} | ${r.problems.length ? r.problems.join("; ").replace(/\|/g, "/") : "OK"} |`),
        "",
      ];
      fs.writeFileSync(path.join(root, reportPath), lines.join("\n"));
      console.log(`REPORT ${reportPath}`);
    }
  } finally {
    await conn.end();
  }
}

if (process.argv[1] && import.meta.url.endsWith(path.basename(process.argv[1]))) {
  main().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
