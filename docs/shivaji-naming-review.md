# "Chhatrapati Shivaji Maharaj" naming: what changed and what needs teacher review

Requested by the research guide (22 Oct 2026): student-facing generated text should say "Chhatrapati Shivaji Maharaj".

## Changed automatically (generated text only)
- `rag/engine/naming.py` rewrites a bare "Shivaji" to "Chhatrapati Shivaji Maharaj" in chat answers, learning-module
  text and titles, and the learning-module PDF body (`rag/internal_api.py`).
- Not changed: verbatim textbook excerpts in Sources, any text inside quotation marks, "Shivaji II", "Shivaji Maharaj",
  and words such as "Shivajinagar". Citations (chapter/page) are not touched.
- The tutor prompt (`rag/prompts/tutor.py`) also asks the model to use the full name in its own sentences.
- Tested by `scripts/naming_unit.py` (9/9). The live answer service picks this up only after a restart (needs approval).

## Not changed: approved quiz questions (teacher decision)
Approved/published quiz content is never edited automatically. These 11 published questions mention "Shivaji"
(read from a copy of the database on 22 Oct 2026). The teacher may decide whether to edit them in the Question bank:

| Question id (start) | Topic | Prompt |
|---|---|---|
| c5d2edc3 | Mughal and Maratha rulers | Match each ruler with what the textbook says about them. (in options) |
| 2241706a | Sher Shah and his administration | Which title did Sher Shah earn for his impartial justice? (in options/explanation) |
| 12a47696 | Shivaji | Shivaji's mother was ______. |
| 136357fb | Shivaji | Where did Shivaji's coronation take place in 1674? |
| 3223d9da | Shivaji | Under the Treaty of Purandar, Shivaji surrendered 23 forts. |
| 553a3cca | Shivaji | Where was Shivaji born? |
| f1b28b8b | Shivaji | Who was Shivaji's guru who trained him in armed warfare? |
| 10fb825d | Shivaji's administration | Shivaji's revenue system was the Ryotwari system, which was favourable to farmers. |
| 281431d6 | Shivaji's administration | What were the ministers in Shivaji's central government called? |
| 504f5b8a | Shivaji's administration | Persian was the language of administration in Shivaji's kingdom. |
| eec45aff | Timeline | Put these events in time order (earliest first). (in options) |

Editing a published question changes what later students see; existing attempts keep their stored answers.
