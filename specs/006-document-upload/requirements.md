# 006 — Document upload: chapters from PDFs and photos

## 1. Introduction

Spec 005 lets a student add a chapter by pasting text. Most course material does not exist as text the student can copy: it is a scanned « cours à trous » with the blanks filled by hand, a photocopied exercise sheet, a photo of a notebook page, a PDF exported from a scanner. This epic makes uploading that material — one PDF or a set of photos — **the** way to add a chapter; pasting text is removed. A **transcription** stage reads every page with a vision model and produces the chapter's source text; the authoring pipeline of spec 005 then runs unchanged on it. The transcription stays readable and editable, so a misread passage can still be corrected as text.

A trial on `courses/chapitre_1.pdf` (16 scanned pages, typed course plus handwritten answers, no text layer) validated the approach: all pages transcribed in 43 s for 0,49 USD, formulas in LaTeX, 287 handwritten passages marked, 4 illegible passages marked, and the pack authored from it on first attempt (160 s, 0,46 USD) with 13 « Points à vérifier » citing pages, several of them real errors in the corrections. The one serious defect: an ambiguous handwritten figure (330 or 350) was transcribed with no doubt marker. `scripts/transcribe_trial.py` is the trial.

Vocabulary:

- **Document** — what the student uploads for one chapter: one PDF, or 1–N images (photos or scans), in page order.
- **Page** — one PDF page or one image.
- **Transcription** — the source text produced from a document: Markdown with LaTeX, a `--- page N ---` marker per page, handwriting marked `[manuscrit]`, doubtful readings `[incertain: …]`, unreadable passages `[illisible]`, figures `[figure : …]`, struck-through text `[barré: …]`.
- **Transcription stage** — the new first stage of an authoring run when the chapter comes from a document.

Scope:

- Upload a PDF or images as the only way to add a chapter (the paste form and its route are removed), and to replace a chapter's source.
- Transcription stage before the pack stage, in the same run, with the same states, limits, retry and failure handling as spec 005.
- The transcription becomes the chapter's source text, readable and editable as text.
- Authoring prompts aware of page markers and handwriting.
- Limits on file size, page count and format; cost and timing recorded per run.

Out of scope:

- Photographing the student's own work to have it checked (brief §6.4 « Read their work »): a different flow.
- Keeping the uploaded file after transcription, showing the scan next to the transcription, or re-transcribing later from the stored file.
- Uploads for subjects other than those available (mathematics, physics).
- A camera capture UI beyond the browser's native file picker (which offers the camera on phones).
- Office formats (DOCX, PPTX), handwritten-only notes without a course, audio or video.
- **Appending pages to an existing chapter** (the student photographs a few new pages and adds them; the pack and path are updated from the new pages without redoing the chapter, ideally keeping progress on unchanged sections). Planned as a later spec; this epic must not block it (NFR 4.1.5).

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §3.1 The student receives typed notes, « cours à trous », handouts, exercise sheets | Material arrives as paper or scans far more often than as copyable text; upload makes the product usable with what students actually hold. |
| §5.7 Setup is minutes, not hours | Photographing or uploading a chapter is faster than retyping it; no manual transcription step. |
| §5.2 The content is the student's; §8 No invented content | The transcription is faithful and marks what it cannot read rather than guessing; the student can correct it before or after the chapter is prepared. |
| §10 Risk: pasted material is incomplete or messy (PDF copy, missing figures) | Figures and tables are described from the page image instead of being lost in a copy-paste. |
| §6.2 « Uploading a PDF or photographed pages is a later input for the same pipeline » | Delivered, and it becomes the only input: pasting is removed. |
| §8 Privacy | The uploaded file is not kept once transcribed. |
| §8 Cost control | Page and size limits, per-run cost recorded; the daily authoring quota applies. |

Deviations: brief §6.2 describes adding a chapter by pasting text. This epic replaces pasting with uploading; §6.2 and §6.8 of the brief are updated accordingly.

## 3. Requirements

### R1 — Upload a document for a new chapter

**As a** student, **I want** to add a chapter by uploading the PDF or photos of my course, **so that** I do not have to retype material I only have on paper.

Acceptance criteria:

1. « Ajouter un chapitre » is an upload form: one PDF, or one or more images (JPEG, PNG, WebP); on a phone the native picker offers the camera. There is no paste form any more; the JSON `POST …/chapters {source_text}` route of spec 005 is replaced by the upload route.
2. Images can be reordered and removed before submission; their order is the page order. A PDF is taken in its own order.
3. The form shows, before submission, the number of pages and the limits: at most `DOCUMENT_MAX_PAGES` pages (default 30) and `DOCUMENT_MAX_BYTES` per upload (default 25 MB). Out-of-limit documents cannot be submitted; the API refuses them with 413 or 422 and a French message.
4. Refused before any model call, with a French message naming the reason: an encrypted or unreadable PDF, a file whose content is not the declared format, an empty document, a page of an image below `DOCUMENT_MIN_PIXELS` on its shorter side (default 800 px).
5. Submitting creates the chapter in `generating` state as spec 005 R2.3 did for pasted text; the student can leave the page.
6. Adding a chapter counts against the same limits as before: chapters per course, runs per student at once, runs per day (spec 005 R2.4, R9).
7. Chapters created before this epic, and the seed of spec 005 R11, keep their text source; nothing is migrated.

### R2 — Transcription

**As a** student, **I want** my pages read faithfully, handwriting and formulas included, **so that** the chapter Célestin teaches is my course and not a guess at it.

Acceptance criteria:

1. Each page is rendered or normalised to an image at a configured resolution and sent to a vision model, several pages per call, calls in parallel under the process-wide authoring limit (spec 005 R9). The transcription model is configurable (`TRANSCRIPTION_MODEL`).
2. The transcription follows the conventions of §1: page markers for every page in order, Markdown structure, LaTeX formulas copied exactly (letters, indices, decimal commas), handwriting marked `[manuscrit]` (inline `[manuscrit: …]` for filled blanks), `[illisible]`, `[incertain: lecture]`, `[figure : …]`, `[barré: …]`. Nothing is summarised, reordered, corrected or added.
3. **Doubt is marked.** Any handwritten digit, sign or number that could be read two ways is transcribed as `[incertain: lecture]`, never as a confident reading. A committed evaluation fixture from `courses/chapitre_1.pdf` p. 5 (the boxed 330/350) must come out marked uncertain in the live evaluation (NFR 4.4.4).
4. A PDF page that has a usable text layer may pass that text to the model alongside its image as a hint; the image stays the reference (text layers of formulas are often wrong).
5. The transcription is validated mechanically: one marker per page, in order, none missing; each page non-empty or explicitly `[page vide]`. A batch that fails validation or is cut short by the output limit is retried once; if it fails again the run fails with code `transcription_failed` (French message: the pages could not be read, try clearer photos or fewer pages).
6. The joined transcription becomes the chapter's source text, subject to `CHAPTER_TEXT_MAX_CHARS` (spec 005); a transcription over the limit fails the run with a message suggesting to split the document into two chapters.
7. Pasted material or text inside the images is data, never instructions (spec 005 R3.8), at the transcription stage as at the others.

### R3 — Authoring from a transcription

**As a** student, **I want** the chapter prepared from my transcription with the same care as from pasted text, **so that** uploading does not give me a worse chapter.

Acceptance criteria:

1. After transcription, the run continues with the pack stage and the curriculum stage of spec 005 on the transcription, with the same validation, repairs, adoption and failure behaviour.
2. The authoring pack prompt says: typed text is the course and is authoritative; `[manuscrit]` passages are the student's or the teacher's handwriting, used for filled blanks and corrections but checked like any correction; `[incertain]` and `[illisible]` passages are never taught as certain and go to « Points à vérifier »; points cite their page (« p. 5 »).
3. A run that fails at the pack or curriculum stage keeps its transcription as the chapter's source text, so « Réessayer » starts from the pack stage and does not pay for transcription again.
4. A run that fails at the transcription stage leaves the chapter's previous content and source text untouched (spec 005 R5.4); « Réessayer » needs the document again (it is not kept, R5).

### R4 — Chapter states and progress during transcription

**As a** student, **I want** to see that my pages are being read and how far it got, **so that** a longer preparation does not look stuck.

Acceptance criteria:

1. While a run transcribes, the course page and the lesson's preparation card say « Lecture des pages… (n/N) », updated by the existing polling; then « En préparation… » for the pack and curriculum stages.
2. The run records its stage (`transcription`, `pack`, `curriculum`) as it progresses; the chapter row exposes the pages read so far and the page count while transcribing.
3. Failure messages name the stage in student terms (pages could not be read / text could not be organised / service unavailable), per spec 005 R4.3.

### R5 — The uploaded file

**As a** student, **I want** my scans not to be kept longer than needed, **so that** my notes and handwriting do not sit on a server.

Acceptance criteria:

1. The uploaded file lives only as long as its run: held in memory or a temporary file for the transcription stage, deleted when the transcription stage ends (success or failure) and on process restart.
2. It is never written to the database, the logs or any persistent storage, and never sent anywhere but the transcription model with `store=false`.
3. After transcription, the chapter's « Texte collé » tab reads « Texte extrait du document » (same editor, same re-preparation behaviour as spec 005 R5.4), and states that the file itself was not kept.

### R6 — Replacing a chapter's source by a document

**As a** student, **I want** to replace a chapter's material with a new upload, **so that** I can fix a bad scan or add the missing pages.

Acceptance criteria:

1. The source tab of « Contenu du chapitre » offers « Remplacer par un document »; it starts a run from the transcription stage with the same limits and confirmation as a source replacement (spec 005 R5.4, R5.5).
2. Editing the transcription as text stays possible (spec 005 R5.4): it is how a misread passage is corrected, and it re-prepares the chapter from the pack stage without transcribing again.
3. While a run is in progress the current content stays in use and the editors are locked, as in spec 005.

### R7 — Cost and observability

**As the** operator, **I want** transcription cost and quality recorded, **so that** I can judge the feature and tune resolution and model.

Acceptance criteria:

1. The run row records, in addition to spec 005 fields: source kind (`text` or `document`), page count, transcription ms, transcription tokens and the transcription share of `cost_estimate_usd`; and the counts of `[manuscrit]`, `[incertain]`, `[illisible]` markers.
2. Log lines `authoring_stage` for the transcription stage per batch (pages, ms, tokens, ok) and the run-level lines of spec 005 carry the same fields. No page image, transcription text or file name in any log.

## 4. Non-functional requirements

### 4.1 Architecture

1. Transcription is a stage of the existing `AuthoringAgent` / `AuthoringRunner` (spec 005), not a separate pipeline: same run row, states, limits, semaphore, timeout policy, orphan handling. The runner accepts either a source text or a document.
2. PDF rendering and image normalisation live behind one module with a permissively licensed library (e.g. `pypdfium2` + Pillow; not AGPL); the vision call goes through the provider seam (`openai` stays in `app/providers/`).
3. Upload is a multipart request on its own route(s), outside the 1 MiB JSON body cap of spec 005, with its own size cap enforced while streaming, before the file is parsed.
4. The frontend upload form replaces the paste form on the course page, within the frontend's existing conventions (spec 005 R10.5).
5. **Not blocking appending pages later** (§1 out of scope): the transcription keeps its per-page markers and records which upload each page came from; the run model keeps « source kind » and stage open to an « append » run that transcribes only the new pages and updates the existing pack and path from them. Nothing in this epic assumes a chapter's source is produced in a single upload.

### 4.2 Performance

1. A 16-page scanned chapter is transcribed in under 90 s wall time in the common case (trial: 43 s), with batches in parallel.
2. Transcription cost stays under 0,05 USD per page at the default resolution (trial: ~0,03 USD); the design picks resolution and image detail with this bound and R2.3 in mind.
3. The run timeout of spec 005 (600 s) covers transcription plus authoring for a document at the page limit; the design adjusts the default if needed and documents it.

### 4.3 Security and privacy

1. Uploaded files are untrusted: size capped before reading, format checked by content (magic bytes), PDFs opened with limits (pages, decompression, no scripts, no external references), rendering isolated from the event loop and bounded in time.
2. The file is deleted per R5; a startup sweep removes any temporary file left by a crash.
3. Uploads are owner-scoped and pass the same-origin check like every mutating route; rate limits of spec 005 apply.
4. No image, transcription or file name in logs (R7.2).

### 4.4 Reliability and quality

1. A transcription batch failure never leaves a chapter in `generating` after the run ends (spec 005 NFR 4.4.2).
2. Offline tests drive the transcription stage with a scripted fake provider and rendered test documents (a generated PDF with a text layer, a scanned-style image PDF, images), covering validation, retry, limits, failure codes and retry-from-pack.
3. The live evaluation script (successor of `scripts/transcribe_trial.py`) runs on `courses/chapitre_1.pdf` and on a set of photos, and reports pages, markers, uncertain/illegible counts, time, cost and the authoring outcome.
4. Evaluation acceptance on `courses/chapitre_1.pdf`: every page transcribed, the p. 5 boxed answer marked `[incertain]`, the dot pattern (c) read `1 ; 4 ; 9 ; 16 ; 25 ; 36`, the pack authored on first or second attempt.

### 4.5 Usability

1. French copy throughout; the upload form explains what works best (one page per photo, flat, lit, whole page visible).
2. Page thumbnails before submission for images; a PDF shows its name and page count.
3. Upload and form usable at 400 px wide; keyboard and screen-reader accessible (reorder by buttons, not only drag).

## 5. Open questions for the design

1. Transcription model and image detail: the authoring model with `detail: high` at 150 dpi (trial) versus a smaller or cheaper vision model; decided on the evaluation of NFR 4.4.3–4.4.4.
2. Batch size (trial: 2 pages) and whether a second, targeted pass re-reads handwritten numbers to enforce R2.3.
3. Whether HEIC photos (iPhone) are accepted and converted server-side, or left to the browser's conversion.
4. Whether the transcription stage should also be offered for pasted text copied from a PDF with broken formulas (out of scope unless trivial).
