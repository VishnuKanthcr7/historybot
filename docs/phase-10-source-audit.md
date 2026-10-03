# Phase 10 — Source audit

**Status:** AUDIT ONLY. Nothing was ingested. Chroma, MySQL, RAG, backend, frontend, and existing extracts were not modified.

**Date:** 4 October 2026  
**Primary (currently ingested):** `data/textbooks/KSEEB-Class-9-Social-Science-Part-2-Textbook.pdf`  
**New folder:** `data/textbooks/sources/` (8 PDFs)

Extraction used PyMuPDF selectable text only. No OCR, no chunking, no embeddings.

---

## Inventory

| File | Size | PDF pages | Extractable text | What it is |
|---|---:|---:|---|---|
| `KSEEB-Class-9-Social-Science-Part-2-Textbook.pdf` (existing) | 1.8 MB | 160 | Yes (Unicode English) | Older KTBS Class 9 Social Science Part 2 (English). Metadata author **BYJU'S**, created 2019 / modified 2020. Cover: Banashankari address. History starts at **Chapter 5 — THE MOGHULS AND THE MARATHAS** (printed pp. 1–14). This is the file HistoryBot already ingested (PDF 3–16 only). |
| `9th English SS Part - 2 2026-27.pdf` | 9.7 MB | 152 | Yes (Unicode English) | **2026–27 KTBS Class 9 Social Science Part 2, English medium.** Cover: Karnataka Textbook Society, 6th Cross, Malleshwaram, Bengaluru 560 003. Footer `@KTBS NOT TO BE REPUBLISHED`. PDF dates March–May 2026. History starts at **Chapter 17**. |
| `9th Kannada SS  Part-2 2026-27.pdf` | 11.2 MB | 136 | Text exists but **not Unicode Kannada** | **2026–27 KTBS Class 9 Social Science Part 2, Kannada medium.** Same KTBS Malleshwaram imprint and `@KTBS` footer. PDF dates February–May 2026. History starts at **Chapter 17** (Nudi-encoded). Filename has a double space before `Part-2`. |
| `The Mughals.pdf` | 1.9 MB | 10 | Partial (CID fonts; some words dropped) | School chapter **“THE MUGHALS (16th TO 17th CENTURY)”**, printed pages 39–48. Metadata: author `ciet`, title `Unit 1 to 4.pdf`, Microsoft Print to PDF (May 2024). This is the NCERT Class 7 *Our Pasts* Mughal chapter (or a CIET print of it), not a Karnataka Class 9 book. |
| `The marathas.pdf` | 5.4 MB | 22 | Yes (Unicode English) | NCERT *Exploring Society: India and Beyond*, **Grade 8 Part 1**, chapter **“The Rise of the Marathas”** (printed ~61–82). InDesign 2026; footer **Reprint 2026–27**. |
| `2d239-the-mughal-empire.pdf` | 7.1 MB | 7 | Yes, dense English | **VisionIAS UPSC “Quick Revision” Module #50 — The Mughal Empire (1526–1857).** Last page is 2025 prelims advertising. |
| `4839a-maratha-empire.pdf` | 4.9 MB | 6 | Yes, dense English | **VisionIAS UPSC “Quick Revision” Module #53 — Maratha Empire.** Same advertising last page as the Mughal module. |
| `The mughalss.pdf` | 2.5 MB | 28 | Sparse (~490 chars/page) | Informal notes on **Mughal-period dress, textiles, miniature painting, jewellery**. Created by Online2PDF.com. Comic Sans / Algerian. **4,704 embedded images.** Not a political-history textbook. |
| `Who was Shivaji_.pdf` | 129 KB | 2 | Yes | **HistoryBot-generated e-content PDF** (ReportLab; author `HistoryBot`). Same 128,746-byte English Shivaji module produced in Phase 9B. Not an external source. |

---

## 1. 2026–27 English Class 9 Karnataka textbook

**File:** `data/textbooks/sources/9th English SS Part - 2 2026-27.pdf`

This is the official **KTBS Ninth Standard Social Science Part 2, English medium, 2026–27**.

Evidence:

- Cover: Government of Karnataka / Karnataka Textbook Society / Ninth Standard / PART 2 / English Medium.
- Contents page uses the 2026–27 chapter numbering (History **17–20**, then Political Science, Sociology, Geography, Economics, Business Studies).
- Chapter 17 title: **THE AHOM DYNASTY, THE Mughals AND THE MARATHAS** (printed pages 1–18; PDF pages 3–20).
- Chapter 18: BHAKTI PANTHA (printed p. 19).
- Creation/mod dates in 2026; `@KTBS NOT TO BE REPUBLISHED`.

It is **not** a byte-for-byte reprint of the currently ingested book.

---

## 2. 2026–27 Kannada Class 9 Karnataka textbook

**File:** `data/textbooks/sources/9th Kannada SS  Part-2 2026-27.pdf`

This is the official **KTBS Ninth Standard Social Science Part 2, Kannada medium, 2026–27**.

Evidence:

- Cover uses the same KTBS Malleshwaram address and `@KTBS` mark.
- Contents: History chapter **17** at printed page 1, chapter **18** at printed page 17 — parallel to the English 2026–27 book.
- Chapter 17 heading (Nudi): `CzsÁåAiÀÄ - 17` / `CºÉÆÃªÀiï gÁdªÀÄ£ÉvÀ£À, ªÉÆWÀ®gÀÄ ªÀÄvÀÄÛ ªÀÄgÁoÀgÀÄ` (Ahom dynasty, Mughals and Marathas).
- Chapter 18 starts at PDF page 19 (`CzsÁåAiÀÄ - 18` / Bhakti).

**Blocker for RAG:** body fonts are **Nudi01e / Nudi01eBold**. PyMuPDF extracts Nudi ASCII, **zero Unicode Kannada code points** in the first ten pages. Ingesting this file as-is would store garbage like `CzsÁåAiÀÄ` instead of ಕನ್ನಡ. A Nudi→Unicode conversion step would be required before any future Kannada ingest. That work is out of scope for this audit.

---

## 3. Best detailed Mughal supplementary source

**Recommended:** `The Mughals.pdf` (NCERT / CIET Class 7 chapter, printed 39–48).

Why this over the VisionIAS Mughal module:

- It is a **school textbook chapter**, closer to HistoryBot’s Class 9 audience than UPSC coaching notes.
- It adds structure the Karnataka chapter treats lightly: Timurid/Mongol lineage, coparcenary succession, **mansab / zat**, **jagirs**, **zabt**, **sulh-i kul**, zamindars, peasant revolts, Nur Jahan.
- 10 pages of connected prose, not bullet cram sheets.

Caveats (quality):

- Microsoft “Print to PDF”; CID fonts.
- Opening sentence is **cropped** (“Ruling as large a territory as the Indian subcontinent with such a diversity of people and cultures was an the Middle Ages”).
- Some later sentences drop words (typical of print-to-PDF).
- Scope stops in the 16th–17th centuries; it does **not** cover 1707–1857.

`2d239-the-mughal-empire.pdf` is **more fact-dense** (Panipat, Khanwa, Ghagra, Haldighati, later Mughals, Sayyid brothers) but it is **UPSC Quick Revision**, ends in **ads**, uses **Babur** spelling, and extends to **1857** — outside the Karnataka Class 9 chapter frame. Use only as optional teacher/exam notes, not as a student RAG source.

`The mughalss.pdf` is **not** a Mughal-empire history source (costume/craft only).

---

## 4. Best detailed Maratha supplementary source

**Recommended:** `The marathas.pdf` (NCERT Grade 8 *Exploring Society: India and Beyond*, Reprint 2026–27).

Why:

- 22 pages vs 6-page VisionIAS sheet and ~5 Maratha pages in the KTBS chapter.
- Connected narrative: Marathi identity, bhakti background, Shivaji’s navy, Agra visit, Sambhaji, Peshwas, **chauth / sardeshmukhi**, forts, trade, Maratha women (Tarabai, Ahilyabai), Thanjavur Marathas, Modi script.
- Clean Unicode text; Noto fonts; reprint marked 2026–27.

Caveats:

- **Grade 8 national textbook**, not Karnataka Class 9. Spellings and emphasis differ (`Chhatrapati Shivaji`, guerrilla narrative, extra biographies).
- Must remain **secondary** so HistoryBot does not overwrite KTBS facts or page citations.

`4839a-maratha-empire.pdf` is useful as a compact UPSC cheat-sheet (Ashtapradhan, Pratapgarh, Purandar, Peshwas, Scindia/Holkar) but last page is advertising and the tone is not classroom prose.

`Who was Shivaji_.pdf` is **not** a supplementary source.

---

## 5. Duplicates / revision material

| Item | Verdict |
|---|---|
| Current ingested PDF vs `9th English SS Part - 2 2026-27.pdf` | **Edition pair, not duplicates.** Older book: 2019/2020 BYJU’S-tagged file, Chapter **5**, spelling **Moghuls**, Banashankari address, 160 pages. 2026–27 book: Chapter **17**, Ahoms added, mixed **Mughal/Moghul** spelling, Malleshwaram address, 152 pages. Mughal–Maratha core is a **revision** of the same KTBS chapter, not a copy. |
| English 2026–27 vs Kannada 2026–27 | **Language editions of the same 2026–27 Part 2**, not duplicates. Same chapter 17 topic and parallel page starts. |
| `2d239-the-mughal-empire.pdf` and `4839a-maratha-empire.pdf` | Same VisionIAS “Quick Revision” product line. Last pages are **identical 2025 prelims ads**. |
| `The Mughals.pdf` vs VisionIAS Mughal module | Overlapping emperors; different genre (NCERT chapter vs UPSC notes). Not file duplicates. |
| `The Mughals.pdf` vs `The mughalss.pdf` | Not duplicates. Political/admin chapter vs costume notes. |
| `Who was Shivaji_.pdf` | **Accidental copy of HistoryBot output.** Same ReportLab module as Phase 9B (`Who was Shivaji?`, textbook pages 10, 11, 13). Do not treat as a new source. |

Revision / coaching material (should not become primary RAG):

- Both VisionIAS modules (plus their ad pages).
- `The mughalss.pdf` (wrong subject).
- `Who was Shivaji_.pdf` (self-generated).

---

## 6. Useful additional details (by topic)

Relative to the **currently ingested Chapter 5** (printed 1–14).

### Already in the old KTBS chapter (do not treat as “new facts”)

Babar/Babur and 1526 Panipat; Humayun / Sher Shah (shorter in the old book); Akbar, Haldighati, Din-e-Ilahi, Hindu policy, Todarmal; Jahangir / Shahjahan / Taj Mahal; Aurangzeb; Shivaji (Shivaneri/Shivneri, Jijabai, guerrilla, Agra escape, Raigad, administration / Swaraj and Moghul areas); later Marathas including Madhav Rao I and Hyder Ali / Srirangapatna.

### New in 2026–27 KTBS Chapter 17 (highest priority if HistoryBot is updated)

Printed pages **1–3 (PDF 3–5):** **Ahom dynasty** — Sukaphaa (1228), Charaideo, Lachit Borphukan, Itakhuli, Guwahati, Alboi, **Saraighat (1671)**, Gadadhar Singha (1682), Manas River, six capitals, 1228–1826, “defeated the Mughals 17 times.” This unit **does not exist** in the ingested Chapter 5. Exercises now ask for Ahom founder and Ahom map work.

Printed pages **4–5:** **expanded Sher Shah** — Farid Khan / Sur clan, four *diwans*, four highways including Sadak-e-Azam, 1700 sarais, Dam and Rupiya, “Sultan of fair justice,” land classes and tax share. The old book mentions Sher Shah more briefly.

Spelling shift in running text toward **Mughal / Babur**, while boxed “Do you know this?” still says **Babar** and *Tuzuk-e-Babari*. HistoryBot currently follows the old **Moghul / Babar** spellings.

Chapter 17 then continues Mughals + Marathas through printed p. 17 and exercises on p. 17–18 (PDF 19–20), then Chapter 18 Bhakti — same succession as old Chapters 5–6, renumbered.

### Useful if a *labelled supplementary* layer is added later

From `The Mughals.pdf`: mansabdari/zat, jagir vs salary problem under Aurangzeb, zabt, sulh-i kul (quoted via Jahangir), Nur Jahan, zamindar–peasant tension.

From `The marathas.pdf`: navy and west coast; *wagh nakh* / Afzal Khan; slave-trade prohibition; chauth and sardeshmukhi as **named taxes**; Tarabai and Ahilyabai; Thanjavur Marathas; Modi script. Several of these are **absent** from KTBS Class 9 and must not silently replace textbook wording.

From VisionIAS modules (exam extra only): battle lists (Khanwa, Chanderi, Ghagra, Pratapgarh, Purandar), Ashtapradhan named as such, Kanhoji Angre, later Mughals 1707–1857, Scindia/Holkar. High conflict risk with Class 9 scope.

### Not useful for HistoryBot history answers

`The mughalss.pdf`: jamdani, shawls, dancing-lady costume notes, Peacock Throne as craft example. Wrong course unit.

---

## 7. Obvious quality / placeholder problems

1. **`Who was Shivaji_.pdf`** — placeholder/self-copy. Includes the weak Kannada line `ಬ್ರೇವ್ ಮತ್ತು ಕಲ್ಲು ರಾಜಾ` from the Phase 9B generator. Remove from `sources/` before any ingest.
2. **Kannada 2026–27 PDF** — Nudi encoding. Unusable for Unicode RAG without conversion. Visual glyphs in a PDF reader may look correct; extracted text does not.
3. **`The mughalss.pdf`** — Online2PDF conversion; mixed decorative fonts; 4,704 images; thin text; filename typo (`mughalss`). Treat as junk for this product.
4. **VisionIAS PDFs** — “Quick Revisi n” (broken glyph in “Revision”); city header spam on every page; **page 7 / 6 are advertisements** (Lakshya Prelims 2025). Not KTBS. Spelling **Babur**, empire dates **1526–1857**.
5. **`The Mughals.pdf`** — print-to-PDF crop; missing words; CID fonts. Still the best *school* Mughal extra, but needs a cleaner official NCERT PDF if used.
6. **Existing primary PDF** — third-party **BYJU'S** metadata on a 2019 KTBS file. Fine as the current prototype source; it is **not** the 2026–27 prescribed edition.
7. **2026–27 English** — mixed capitalisation in contents (`MuGHULS`, `communitY`); mixed Babar/Babur. Typical KTBS layout artifacts, still the correct prescribed English book.
8. **No OCR needed** for English 2026–27, old English, Grade 8 Marathas, or VisionIAS body pages. Kannada needs encoding conversion, not OCR. `The Mughals.pdf` may benefit from a better source file rather than OCR.

---

## 8. Recommended source hierarchy for HistoryBot

Do **not** ingest yet. When a later phase ingests, use this order.

### Tier 0 — Student-facing ground truth (prescribed)

1. **`9th English SS Part - 2 2026-27.pdf`**, **Chapter 17 only** (printed 1–18 / PDF 3–20), as the **new English primary** if the product moves to 2026–27.
2. **`9th Kannada SS  Part-2 2026-27.pdf`**, **Chapter 17 only**, as the **Kannada primary**, **after** Nudi→Unicode conversion. Until then, keep answering Kannada questions from English evidence (current Phase 9 behaviour).

Citation pages must be **printed textbook pages of this edition**, not the old Chapter 5 numbers (old printed 1–14 ≠ new printed 1–18 once Ahoms occupy the front).

### Tier 0b — Legacy (current production)

3. **`KSEEB-Class-9-Social-Science-Part-2-Textbook.pdf` Chapter 5** remains the **live Chroma source** until a planned re-ingest. Do not mix old Chapter 5 chunks and new Chapter 17 chunks in one collection without a new `ingest_version` and citation map.

### Tier 1 — Optional labelled supplements (never override KTBS)

4. **Maratha extra:** `The marathas.pdf` (Grade 8 NCERT chapter), cited as Grade 8 supplementary, not as “textbook page N” of Class 9.
5. **Mughal extra:** `The Mughals.pdf` (Class 7 NCERT chapter), same labelling rule; prefer a cleaner official PDF if obtained.

### Tier 2 — Do not put in student RAG

6. VisionIAS modules — teacher/exam crib only; strip ad pages if ever indexed privately.
7. `The mughalss.pdf` — exclude.
8. `Who was Shivaji_.pdf` — exclude and delete from `sources/`.

### Product rule

Student answers should stay **KTBS Class 9 Chapter 17 (2026–27)** or, until re-ingest, **old Chapter 5**. Supplements may add a clearly marked “additional school-book detail” layer later. They must not invent Wikipedia facts and must not change Class 9 page citations.

---

## Comparison snapshot: old Chapter 5 vs 2026–27 Chapter 17

| | Current ingested book | 2026–27 English book |
|---|---|---|
| Part 2 history opener | Chapter **5** THE MOGHULS AND THE MARATHAS | Chapter **17** THE AHOM DYNASTY, THE Mughals AND THE MARATHAS |
| Printed span | 1–14 | 1–18 |
| Next chapter | 6 Bhakti Panth (printed 15) | 18 Bhakti Pantha (printed 19) |
| Ahoms | Absent | ~3 pages + exercises |
| Sher Shah | Short | Expanded admin, roads, coinage |
| Mughals + Marathas core | Present | Present, revised wording/spelling |
| Exercises | Old set | Adds Ahom items; keeps Babar/Akbar/Taj/Din-e-Ilahi/Jijabai/Shivaji/Bajirao |

Kannada 2026–27 Chapter 17 matches the English 2026–27 topic list (Ahoms + Mughals + Marathas), not the old English Chapter 5-only scope.

---

## Out of scope (not done)

- No Chroma rebuild or ingest
- No MySQL / RAG / API / frontend changes
- No Nudi converter
- No deletion of files (recommendation only: remove `Who was Shivaji_.pdf` from `sources/`)

**STOP.** Next implementation phase should not start until this hierarchy is approved.
