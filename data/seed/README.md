# Seed data (generated — do not edit by hand)

Regenerate with `npm run seed:generate`; load into SQLite with `npm run seed`.

- `canvas_json/courses/<id>/` — data in Canvas REST API response shapes, as
  `CanvasJsonAdapter` would receive it from `/api/v1/...`. File `url`s are paths relative to
  this folder instead of download links.
- `manual/<id>/` — data Canvas does not expose: per-question scores for non-quiz work
  (including scanned exams), homework/exam question definitions, question → outcome
  alignments, material kinds and file metadata (page count, text layer).
- `files/` — lecture PDFs, typed homework uploads and image-only scanned midterms.

All people and content are fictional.
