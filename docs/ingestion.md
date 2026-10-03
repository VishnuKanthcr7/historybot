# Phase 4 — Textbook ingestion

**Status:** COMPLETE (awaiting review before Phase 5 / Chroma).

## Source PDF

- File: `data/textbooks/KSEEB-Class-9-Social-Science-Part-2-Textbook.pdf` (gitignored)
- Title metadata: KSEEB Class 9 Social Science Part 2 Textbook
- Total PDF pages: **160**
- Ingested: **PDF pages 3–16 only** (14 pages)
- Chapter: **CHAPTER – 5 — THE MOGHULS AND THE MARATHAS**
- Not ingested: PDF 1–2, PDF 17+ (Chapter 6 BHAKTI PANTH starts on PDF page 17 / printed page 15)

## Printed-page mapping

`textbook_page_number = pdf_page_number - 2`

| PDF page | Textbook page |
|---:|---:|
| 3 | 1 |
| 4 | 2 |
| 5 | 3 |
| 6 | 4 |
| 7 | 5 |
| 8 | 6 |
| 9 | 7 |
| 10 | 8 |
| 11 | 9 |
| 12 | 10 |
| 13 | 11 |
| 14 | 12 |
| 15 | 13 |
| 16 | 14 |

Both numbers are stored on every page record and every chunk.

## Extraction method

- Library: PyMuPDF (`pymupdf`) already installed on this machine
- Method: selectable text, `page.get_text("text")`, page-by-page
- Cleaning: Unicode NFC, soft-hyphen removal, join `word-<newline>word` hyphenation, join narrow one-word-per-line sidebars, strip the printed page number line, normalize bullets
- **No rewriting of facts** (textbook spellings such as “alomost” / “characterstics” are left as printed)

## OCR

**Not used.** Pages 3–16 all contain extractable text (about 1.1k–2.8k characters each after cleaning). No blank/scanned pages in this range.

## Extraction quality

Acceptable for RAG. Layout artifacts (column/sidebar line breaks, en-dashes) are reduced by cleaning. Meaning is not “corrected” from outside sources.

PDF page 3 begins `CHAPTER – 5` / `THE MOGHULS AND THE MARATHAS`.  
PDF page 16 ends with Chapter 5 **EXERCISES** (fill in the blanks, questions, activities, project work).  
Chapter 6 does not appear in the ingested set.

## Character counts (cleaned)

| PDF | Textbook | Characters |
|---:|---:|---:|
| 3 | 1 | 1841 |
| 4 | 2 | 2187 |
| 5 | 3 | 1760 |
| 6 | 4 | 1147 |
| 7 | 5 | 2247 |
| 8 | 6 | 1934 |
| 9 | 7 | 2152 |
| 10 | 8 | 2030 |
| 11 | 9 | 2149 |
| 12 | 10 | 2355 |
| 13 | 11 | 1227 |
| 14 | 12 | 2531 |
| 15 | 13 | 2759 |
| 16 | 14 | 1859 |
| **Total** | | **28178** |

## Visuals (recorded only — not downloaded, not verified-image system)

Embedded textbook images on pages 3–16:

| PDF | Textbook | Type | Caption guess |
|---:|---:|---|---|
| 5 | 3 | portrait_or_photograph | Akbar |
| 6 | 4 | map | Akbar’s kingdom |
| 8 | 6 | photograph_or_monument | Panch mahal at Fatehpur Sikri |
| 8 | 6 | photograph_or_monument | Taj Mahal |
| 10 | 8 | photograph_or_monument | Red Fort |
| 11 | 9 | portrait_or_photograph | Shivaji |
| 13 | 11 | map | MARATHA KINGDOM / Shivaji ruling areas |
| 14 | 12 | decorative_or_glyph (×2) | Tiny icons (likely fraction glyphs), not maps/photos |

Phase 12 will handle verified student-facing images. Do not substitute internet pictures.

## Chunking

Starting config: **400–700 characters**, **~15% overlap**, **never cross PDF page boundaries**, prefer headings with following text, avoid mid-sentence splits.

Documented adjustments:

- Some chunks are slightly **over 700** (up to ~864) so a sentence/heading is not split.
- A few chunks are **under 400** (lowest 359) when a heading block or page remnant should stay on its own page.
- Chunks never mix two PDF pages, so page citations stay exact.

Run result: **67 chunks**, min 359, max 864, average ~597.

### Metadata (every chunk)

- `chunk_id`
- `document_name`
- `chapter`
- `section`
- `source_file`
- `ingest_version` (currently `1`)
- `pdf_page_number`
- `textbook_page_number`
- `text`
- `char_count`

## How to re-run

```text
python scripts/ingest_chapter5.py
```

Writes (gitignored textbook extracts):

- `data/extracted/chapter5_pages.json`
- `data/extracted/chapter5_chunks.json`
- `data/extracted/chapter5_visuals.json`
- `data/extracted/chapter5_ingest_summary.json`

## Not in this phase

ChromaDB, embeddings, LLM, MySQL changes, frontend, other chapters.
