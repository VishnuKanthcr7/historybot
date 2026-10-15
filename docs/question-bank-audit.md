# Question bank audit

Run: 2026-10-15 (IST). Source of truth: indexed textbook passages in data/quiz/textbook_passages.json (Chapter 17).
Checks: cited excerpt found verbatim in the cited passage; MCQ key stated in the excerpt; distractors not also in the excerpt; duplicate options/prompts; blank present in fill-in items.
Drafts with problems are set to needs_review. Nothing is published by the audit. 'check:' findings are advisory (the teacher should look).

Totals: 41 questions; {"draft":5,"published":36}; 1 with findings; 0 set to needs_review; 2 wording fixes.

| Status | Question | Type | Page | Findings |
|---|---|---|---|---|
| draft | ahom-founder | fill_blank | 1 | OK |
| draft | ahom-capital | mcq | 1 | OK |
| draft | ahom-borphukan | mcq | 2 | OK |
| draft | ahom-saraighat | true_false | 2 | OK |
| draft | order-ahom | order | 1 | OK |
| published | akbar-birth | mcq | 5 | OK |
| published | akbar-age | mcq | 5 | OK |
| published | akbar-panipat2 | mcq | 5 | OK |
| published | akbar-dinilahi | fill_blank | 6 | OK |
| published | akbar-jizya | true_false | 6 | OK |
| published | akbar-subhas | true_false | 7 | OK |
| published | akbar-zabti | true_false | 7 | OK |
| published | aurangzeb-title | mcq | 9 | OK |
| published | babur-panipat1 | mcq | 3 | OK |
| published | babur-language | fill_blank | 3 | OK |
| published | babur-age | true_false | 3 | OK |
| published | humayun-son | true_false | 3 | OK |
| published | akbar-mansab | mcq | 7 | OK |
| published | akbar-dagh | mcq | 7 | OK |
| published | match-rulers | match | 5 | OK |
| published | lit-ain | mcq | 10 | OK |
| published | match-books | match | 10 | OK |
| published | shahjahan-taj | mcq | 8 | OK |
| published | shahjahan-golden | true_false | 8 | OK |
| published | shershah-name | mcq | 4 | OK |
| published | shershah-title | mcq | 5 | OK |
| published | shershah-coin | mcq | 5 | check: distractor "Dam" also appears in the excerpt; confirm the prompt rules it out |
| published | shershah-sarais | true_false | 4 | OK |
| published | shershah-court | true_false | 5 | OK |
| published | shivaji-mother | fill_blank | 13 | OK |
| published | shivaji-born | mcq | 13 | OK |
| published | shivaji-guru | mcq | 13 | OK |
| published | shivaji-purandar | true_false | 13 | OK |
| published | shivaji-coronation | mcq | 14 | OK |
| published | shivaji-ministers | mcq | 14 | OK |
| published | shivaji-ryotwari | true_false | 14 | OK |
| published | shivaji-language | true_false | 14 | OK |
| published | peshwa-bajirao | mcq | 15 | OK |
| published | panipat3 | mcq | 16 | OK |
| published | order-battles | order | 3 | OK |
| published | order-mughals | order | 3 | OK |

## Manual review, 15 Oct 2026: shershah-coin
- **Question:** "Which silver coin did Sher Shah introduce?" Key: Rupiya.
- **Textbook (KTBS Class 9 Social Science Part 2, Ch. 17, p. 5, chunk ktbs2026_en_ch17_pdf7_tb5_02):** "Sher Shah introduced a new coin the Dam (Copper) and Rupiya (Silver) into circulation."
- **Finding:** "Dam" appears in the excerpt but is labelled copper. The word "silver" in the prompt rules it out, so the key is correct and the distractor is fair.
- **Action:** status left unchanged. The question stays flagged in this report for the teacher's attention, and nothing was published or unpublished.

## Duplicate check
- Prompt similarity was compared across all 41 questions.
- The closest pairs are distinct questions on different events:
  - babur-panipat1 / panipat3 (First vs Third Battle of Panipat)
  - order-battles / order-ahom (different event sets; order-ahom is a draft)
  - akbar-birth / shivaji-born
- No duplicates were found, and no answer key is invalid.

## Draft review against the textbook, 15 Oct 2026 (recommendations only; no status changed)

I checked each item against the indexed KTBS Class 9 Social Science Part 2 (English) 2026-27 text, Chapter 17, reading it read-only from data/chroma. The source chunks contain duplicated OCR fragments (e.g. "The Ahom dynasty was founded by Ahom Dynasty Ahoms were…"), but the quoted sentences are present verbatim.

| Key | Source checked | Finding | Recommendation |
|---|---|---|---|
| ahom-founder (fill blank) | ch17_pdf3_tb1_02: "The Ahom dynasty was founded by Sukaphaa in 1228." | The key is correct. The server also accepts the curated Sukaphaa spellings (answerVariants.js). | Ready to publish once the teacher approves. |
| ahom-capital (MCQ) | ch17_pdf3_tb1_02: "Their first capital was Charaideo." | The key "Charaideo" is correct. The distractors (Guwahati, Itakhuli, Saraighat) are chapter place names that are never called the capital, so they are fair. | Ready to publish once the teacher approves. |
| ahom-borphukan (MCQ) | ch17_pdf4_tb2_01: "Lachit, became the commanderin-chief of the Ahom army. This post was called 'Borphukan'." | The key is correct. Peshwa, Hawaldar and Mansabdar are posts from other parts of the chapter, which makes them good distractors. | Optional wording: "What was the post of commander-in-chief of the Ahom army (held by Lachit) called?" Then publish once the teacher approves. |
| ahom-saraighat (true/false) | ch17_pdf4_tb2_02: "a significant naval attack took place at Saraighat in 1671, the Ahoms were victorious." | The statement "The Ahoms won the naval battle at Saraighat in 1671" is TRUE per the text. The book says "naval attack"; "naval battle" is a fair paraphrase. | Ready to publish once the teacher approves. |
| order-ahom (order) | pdf3_tb1_02 (1228), pdf4_tb2_02 (1670, 1671), pdf5_tb3_01: "In 1682, under the rule of Gadadhar Singha, the last battle took place…" | All four dates are in the text, and the order 1228 → 1670 → 1671 → 1682 is correct. The 1670 and 1671 events are adjacent but the years are shown, so this is not ambiguous. | Ready to publish once the teacher approves. |
| shershah-coin (published) | ch17_pdf7_tb5_02: "Sher Shah introduced a new coin the Dam (Copper) and Rupiya (Silver) into circulation." | Re-checked: the key Rupiya is correct, and "silver" in the prompt rules out Dam. | No change needed. The flag can be cleared at the teacher's discretion. |

No draft has a factual error. Publishing is a teacher decision and has not been done. The database was not changed.
