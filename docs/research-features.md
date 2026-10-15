# Research features (migration 006)

Everything in this document is descriptive data collection for a teacher or researcher. Nothing here makes causal claims.

## Data captured (ids, counts, scores and times only; no chat text)
| Event | When it is recorded | Idempotency key |
|---|---|---|
| USER_REGISTERED | after a successful registration | `register:<user>` |
| USER_SIGNED_IN | each successful login | none (each sign-in counts) |
| QUESTION_ASKED / ANSWER_GENERATED | chat turn; counts only | none |
| MODULE_OPENED | first time a student opens a module | `module-open:<user>:<module>` |
| MODULE_COMPLETED | when the student clicks "Mark complete", or submits the module's checkpoint quiz | `module-complete:<user>:<module>` |
| PDF_DOWNLOADED | module PDF served | none (each download counts) |
| QUIZ_STARTED | attempt created | `start:<attempt>` |
| QUIZ_SUBMITTED / QUIZ_TIMED_OUT | attempt finalised; `quiz_attempts.end_reason` = submitted / timed_out | `end:<attempt>` |
| QUESTIONNAIRE_SUBMITTED | first submission of an instrument | `questionnaire:<instrument>:<user>` |

- **Abandoned attempt:** an untimed attempt that is still `in_progress` more than 24 h after it started. This is derived when the data is read and is never stored.
- **Stored per answer:** the response, whether it was correct, and the points awarded (`quiz_answers`).
- **Duplicates:** `analytics_events.idempotency_key` is UNIQUE, so retries and double clicks cannot double count.
- **Dashboard dates:** shown in IST, and the date ranges are inclusive (from 00:00 on the first day to 23:59:59 on the last).
- **Data freshness:** every overview shows "data as of …".
- **Known gap:** a module completed only through its checkpoint quiz has no MODULE_OPENED event.

## Questionnaire instruments
- **Tables:**
  - `research_instruments`: draft, published or archived.
  - `research_items`: Likert scale (2 to 10 points), subscale, `reverse_scored`, required.
  - `research_responses`: one per student per instrument.
  - `research_response_items`.
- **Items:** they cannot be edited once the instrument is published or has any responses.
- **Scoring:** a reverse-scored item is scored as (min + max − value). A missing answer is stored as missing and never as zero. A subscale mean is reported only when at least half of its items are answered; otherwise it counts as "insufficient".
- **Student UI:** `/questionnaires` shows published instruments only. Teachers find results and CSV under Dashboard → Research. The CSV uses pseudonymous `S-xxxxxxxx` ids, marks reverse items with `_R`, leaves missing answers blank, and stamps times in IST.
- **Shells:** "Digital Attitude" and "Social Engagement" are seeded in **draft**. Their placeholder items read "REQUIRES RESEARCHER APPROVAL". They must be replaced with validated, licensed items before publishing, and the placeholders must never be published.

## Pre/post
- A post-test quiz must name its pre-test (`quizzes.pre_quiz_id`) before it can be published.
- Comparisons use **matched students only**: those with a finished attempt on both quizzes, taking the first attempt of each.
- The results report paired n, the pre and post means, the mean gain and its SD, and a paired t with df and two-sided p. These are labelled "descriptive, no control group".
- Students who took only one of the two tests are listed separately as unmatched.

## Collaboration: deliberately not built
- Peer chat, group work or shared spaces would add moderation, safeguarding and privacy duties for minors.
- The research design has not defined what collaboration means or how it should be measured.
- No validated instrument for it has been provided.
- Building it now would produce data with no defined analysis. This can be revisited once the researcher specifies the construct, the measure and the moderation model.

## Question bank
`node backend/scripts/audit-question-bank.mjs [--apply] [--report docs/question-bank-audit.md]` checks the questions:
- whether each excerpt appears verbatim in the passage,
- whether the answer key is valid,
- duplicate options and distractors that also appear in the excerpt,
- wording.

With `--apply`, flagged drafts become `needs_review`. The audit never publishes anything. The UI labels each quiz as Practice / Assessment / Pre-test / Post-test / Draft.

## Which attempts count for each score (why the Shivaji practice quiz showed 40% while the Assessment average showed 0%)
| Metric | Attempts that count | Attempts that do not count |
|---|---|---|
| **Assessment average** (Overview) | The FIRST finished attempt (submitted or timed out) of each student on each teacher quiz in assessment mode, including pre/post tests | Practice quizzes, activities, personal revision/checkpoint quizzes, and later attempts |
| **Practice average** (Overview) | EVERY finished attempt on practice quizzes, activities and personal quizzes | Assessments |
| **Quiz results** (Quizzes → Results) | All finished attempts on that one quiz | Other quizzes |

- **The real case on 15 Oct 2026:**
  - The "Find the Correct Answer: Shivaji and the Marathas" quiz is a practice activity; one student scored 40% on it.
  - The only assessment attempt was on "Chapter 17 Pre-test". It timed out with no saved answers, so it was scored 0%.
  - The Assessment average was therefore correctly 0% (n = 1, 1 timed out). The Shivaji 40% belongs only to the Practice average.
- **What changed in the UI:**
  - The cards are relabelled "Assessment average" and "Practice average".
  - Each card shows its n and how many attempts timed out.
  - A card shows "No data" (never 0%) when no attempt qualifies.
- **Definitions:** unchanged.

## Activity over time
- **Days shown:** every IST day in the selected range is a column, including quiet days.
- **What is counted:**
  - chat questions
  - finished quiz attempts
  - modules opened
  - modules completed
  - PDF downloads
  - sign-ins (in the API only; the chart does not draw them)
- **Day boundaries:** events are bucketed by IST calendar day. An event at 23:59 IST and one at 00:01 IST fall on different days. Tests cover this in `backend/scripts/analytics-unit-test.mjs`.
- **Earlier bug:** the chart was blank because each day column was a flex item with auto height, so the bars' percentage heights resolved to 0.

## Quiz randomisation and retries
- **Practice and regular assessments:**
  - Every attempt uses each question of the same published quiz exactly once, in a server-chosen order.
  - MCQ, ordering and match options are shuffled by stable option ids, so answer keys never change.
  - The layout and its seed are stored on the attempt, so a reload shows the same layout.
- **Pre/post tests:** never randomised, so both forms stay equivalent.
- **Try again:**
  - It creates a new attempt and keeps all earlier ones, which the results page lists.
  - It appears only when the server would accept a new start: the quiz is published, it is inside its open/close window, and the attempt limit is not reached.
  - Double clicks are harmless. The button locks while a start is in progress, and the server serialises starts and resumes any open attempt instead of creating another.

## Pre/post linking rules
- The linked quiz must exist and be a teacher quiz marked pre-test (400 otherwise).
- A pre-test can be linked by only one post-test (409 otherwise).
- A post-test cannot be published until its pre-test is linked and published.
- The Research tab shows, for each pair: both statuses, the number of pre- and post-test takers, the matched n, the unmatched counts and the limitations.

## Kannada support (limitation, 15 Oct 2026)

- The Kannada edition of the Class 9 textbook PDF is set in legacy Nudi fonts: its text layer contains no Unicode Kannada characters, so it cannot be indexed or quoted faithfully.
- Because of this the RAG service refuses Kannada chat answers and Kannada learning modules (`KANNADA_UNAVAILABLE` / `kannada_corpus_unavailable`) rather than machine-translating or inventing content.
- The interface menus are translated. The language selector reads "ಕನ್ನಡ (menus only)", and the chat shows a note asking students to ask questions in English.
- PDF export uses ReportLab, which does not shape Kannada conjuncts. A shaping engine (e.g. HarfBuzz via uharfbuzz) is not installed, and is not needed until a Unicode Kannada source exists.
- To lift the limitation: obtain a Unicode Kannada textbook (or convert Nudi → Unicode with a verified converter), re-index it, then add shaped PDF output and check it by eye against the printed book.
