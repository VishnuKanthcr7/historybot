# "Who was Akbar?" answer audit (15 Oct 2026)

**What was checked:**
- Two stored production answers, read-only: 06a3a4b3 (15 Oct) and 4392bc9a (12 Oct).
- One new answer from the Ollama test RAG. No OpenAI call was made.
- The retrieved Chapter 17 chunks: p.5 (pdf7_tb5_03, pdf7_tb5_04), p.6 (pdf8_tb6_02, pdf8_tb6_04), p.7 (pdf9_tb7_02, pdf9_tb7_04).

## Stored answers (production model)

**Supported under "From your textbook":**
- **p.5:** born in Amarkot (Sindh); father Humayun; age 14 at accession; Bairam Khan as guardian; Hemu took Delhi and Agra; Second Battle of Panipat in 1556.
- **p.6:** Man Singh and Asaf Khan; Haldighati victory; Kashmir, Sindh, Orissa, Baluchistan, Kandahar and Ahmednagar; inspired by his mother, teachers and Sufi saints; tolerance; Rajput wives; Jizya abolished.
- **p.7:** supreme head, commander-in-chief, executive and judiciary; Vakil, Diwan, Mir Bhakshi, Main Sardar; Subhas; Mansabdari; temples; Persian translations; Hindus in high posts; Todarmal; the governors; 8 of 12 provincial finance ministers; Rakhi, Deepavali and Shivaratri.

**Unsupported text that carried the textbook label:**
- "Mansabdari system, a system of official ranks" (06a3) and "…a system of ranks for imperial officers" (4392). The passages do not define Mansabdari.
- "religious tolerance, meaning respect for different religious beliefs" (06a3).
- "judiciary, which administered justice" (4392).

**Correctly uncited:** 1556–1605 and the Jahangir succession. "Din-e-Ilahi" was placed in the supplementary section, but it is actually the heading on p.6, so this is under-attribution.

**Citations:** pages 5, 6 and 7 equal the retrieved pages. No page was cited that was not retrieved.

## New test-RAG answer (after the fix)

- **Textbook part:** fully supported (p.5 and p.7), and the cited pages 5 and 7 match the Sources list.
- **Supplementary part:** contains a misreading by the local model, "Hindu policy was an amalgamation of thoughtfulness … natural forces". On p.6 that phrase belongs to the Din-e-Ilahi paragraph. It is uncited and not labelled as textbook text, but it is wrong.

## Fix

- **`rag/engine/answer.py`, `_split_unsupported_gloss`:**
  - A trailing gloss (", a …", ", meaning …", ", which means …", ", that is …", ", i.e. …") whose content words are mostly absent from the retrieved chunks is cut from the textbook sentence.
  - The cut gloss moves to the uncited supplementary section as "Term: gloss.".
  - Supported glosses stay (e.g. "Jizya, a tax imposed on Hindus").
- **Sources now carry `chapter` and `excerpt`:**
  - The general answer path takes the excerpt from the retrieved chunk text, de-duplicated.
  - The fact-layer path uses the actual textbook sentences that supplied each fact.
  - Both pass through the internal API and the backend's `publicSources`.
  - The chat shows them in an expandable, accessible "Sources" list: chapter, page and a quote.
- **Tests:**
  - `final_unit_tests.py`: 5 checks using the real p.6/p.7 text.
  - `browser_e2e`: the Sources rows have excerpts, and their pages equal the stored citation pages.

## Limits

- The check is lexical: it cannot catch a misread relation that reuses the passage's words.
- The live RAG (:8000) and the live backend (:3000) run the previous code until someone restarts them. They were not restarted, per instruction.
