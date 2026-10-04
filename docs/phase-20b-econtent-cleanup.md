# Phase 20B — E-content evidence cleanup

Student-facing learning-module fields were taking the first raw chunk sentence, including OCR headings such as `MughalS IN INDIA` and `Do you know this?`.

## Change

Only `rag/engine/econtent.py` selection/cleanup (plus tests). Chat `generate_from_plan` is unchanged.

Before filling people, terms, timeline, events, key points, and revision:

- normalize OCR wrappers (duplicate names, heading prefixes, UNESCO leftovers)
- reject incomplete / heading-only sentences
- pick person sentences that actually name the ruler
- include a term only when a sentence explains it; omit Mansab/Jagir/Vakil/Diwan when the pack only lists them among royal duties or ministers
- keep dated events only when the year is in a complete textbook sentence; sort pages numerically

PDF still renders the cleaned JSON.

## Tests

`scripts/phase20b_econtent_cleanup.py`: OCR rejection, page order, plan cleanup, full Mughals module + PDF.
