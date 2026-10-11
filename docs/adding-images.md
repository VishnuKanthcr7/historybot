# Adding textbook images and GIFs

Images are shown next to an answer only when all of these hold:

1. The row in `verified_images` has `verification_status = 'verified'`.
2. The answer cites a textbook page within 1 page of the image's `textbook_page_number`.
3. The image matches the question: a built-in person (Akbar, Shivaji, Babur, Humayun, Sher Shah,
   Shah Jahan, Aurangzeb, Baji Rao, Taj Mahal) by name, any other person by `person_name`
   (e.g. "Tipu Sultan"), otherwise by `topic` text. A question about one person never shows
   another person's image.

## Steps

1. Put the file in `data/images/` (`.png`, `.jpg`, `.jpeg`, `.webp` or `.gif`).
   Use only images from the textbook or with a licence that allows use; record it in `source`/`license`.
2. Add an entry to a manifest JSON array (the default is `data/extracted/chapter5_image_manifest.json`;
   a new chapter can have its own file):

```json
{
  "topic": "Tipu Sultan",
  "person_name": "Tipu Sultan",
  "file_path": "data/images/tipu-sultan.png",
  "caption": "Tipu Sultan",
  "alt_text": "Portrait of Tipu Sultan from the textbook",
  "source": "Class 9 Karnataka State Board textbook",
  "license": "Textbook figure",
  "verified_by": "teacher name",
  "textbook_page": 21,
  "media_kind": "image",
  "verification_status": "verified"
}
```

   `media_kind` is `"gif"` for animations (inferred from the `.gif` extension when omitted).
   Always give `alt_text`: screen readers read it.
3. Check first (no database change):
   `node backend/scripts/seed-verified-images.mjs --manifest <file> --dry-run`
   Items with a problem are listed as `SKIP <file>: <reason>`.
4. Store: `node backend/scripts/seed-verified-images.mjs --manifest <file>`.
   Re-running is safe (rows are matched by `file_path`).
5. No restart is needed; images are looked up per answer. Images are served only to signed-in users.
6. Run `node backend/scripts/auth-media-test.mjs` against a test backend to confirm matching rules.
