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
