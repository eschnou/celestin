# Photographed work: the camera in the composer

The student photographs what she wrote by hand (the answer to an exercise, a calculation) and Célestin reads it
with her. This is the brief's « Read their work » (`specs/product.md`): *the tutor shows what it read, the student
confirms*. It was built without an SDD spec, at the user's request.

## The idea: read it, correct it, send it as text

The tutor **never sees the picture**. A vision model reads the handwriting into text, the text lands in the
message field, the student reads it, fixes it and sends it like any message. Why this and not the picture sent to the
tutor model:

- it keeps the tutor text-only, so it works on any provider's tutor model (not every one takes images), and no
  image is carried in a transcript that the browser re-posts whole every turn (parcours) or that is stored
  (discussion);
- a misreading is the student's to catch **before** it counts: « 330 » read as « 350 » would otherwise turn a right
  answer into a wrong verdict;
- the photo is read and forgotten: nothing is stored, and what she wrote is never logged.

## The route

`POST /api/courses/{course_id}/work` (`api/routes/work.py`, `services/work_reading.py`), multipart with one `photo`
(JPEG, PNG or WebP). The course must be the student's own (`404` otherwise); it gives the **language the work is
written in**. The photo goes through the same `DocumentService.prepare` as an uploaded page (sniffed by its bytes,
decoded in a worker process, turned upright by its EXIF orientation, shrunk to `TRANSCRIPTION_MAX_SIDE_PX`, EXIF
dropped) but with its own minimum size, `WORK_MIN_PIXELS` (400): a webcam's 480p picture is a small photo, not a
refusal, where a course page needs 800. It is then read by the **transcription role** (`hub.authoring_llm.complete(role="transcription")`: the
vision model already configured to read documents, so no new setting) with `prompts/transcription/work.<language>.md`.

That prompt keeps the conventions of the course transcription: faithful, **nothing corrected** (a wrong sign stays
wrong: the tutor is the one who says so), formulas in `$…$`, `[incertain: a | b]` for a digit that could be read two
ways, `[illisible]` rather than a guess, `[barré: …]`, `[figure : …]` for a sketch, only what the student wrote, the
photo's own instructions treated as data. A photo with no writing answers `[rien de lisible]` (`[nothing legible]`),
which the route turns into an empty text. The response is `{"text": "…"}`; empty is `200`, not an error.

Errors: `422 document_invalid` (not an image, unreadable, too small, empty), `404`, `413` (`WORK_MAX_BYTES`, enforced
while the body streams), `429 work_rate_limited` (per user, `WORK_PER_HOUR`), `503 ai_not_configured` (like every route that
calls the provider), and the provider's own. One log line, `work_read`: user, language, bytes in and sent, number of
characters, **number of doubts** (`[incertain:` marks), tokens, estimated cost, latency.

| Variable | Default | Notes |
|---|---|---|
| `WORK_MAX_BYTES` | `12582912` | One photo as the phone made it; the browser sends far less. |
| `WORK_MIN_PIXELS` | `400` | Shortest side. |
| `WORK_MAX_OUTPUT_TOKENS` | `3000` | |
| `WORK_PER_HOUR` | `60` | Per user. |

The model must accept images, as for documents: the admin's live check of the transcription role (`no_image_input`)
says whether it does.

## In the browser

`composer.tsx` shows the camera whenever the lesson or the discussion gives it a `courseId`. It is a menu
(`photo-button.tsx`):

- **On a phone** (`useCoarsePointer`, `(pointer: coarse)`): « Prendre une photo » opens the phone's own camera
  (`<input type="file" accept="image/*" capture="environment">`) and « Choisir une image » its gallery or files.
- **On a computer**: « Prendre une photo » opens the **webcam** (`webcam-dialog.tsx`: `getUserMedia`, a live view,
  « Prendre la photo », then « Refaire » or « Utiliser cette photo »; the camera, and its light, are off as soon as the
  picture is taken or the dialog closes), « Choisir une image » the file chooser. With no webcam the button goes
  straight to the chooser. A blocked camera says so and points to the chooser.

Whichever way the picture arrives, `use-photo-work.ts` prepares it (`lib/tutor/work.ts` `preparePhoto`: upright,
longest side 1800 px, JPEG: a 4 MB phone photo becomes a few hundred kB; the original goes where the browser cannot
decode it, and the server has the last word), posts it, and gives the text to the composer, which writes it in the
field **after what she had already typed**, framed by a sentence in the course's language
(`useLearnerSentences().work`: « Voici mon travail, lu sur ma photo : »), with a note under the field: *read what I
read and correct it; the parts in [brackets] are the ones I'm not sure about.* Nothing is sent for her. While a photo is
being read the camera shows a spinner and the field says « Je lis ton travail… ». An empty reading, a file that is not a
picture and a failure each have a sentence under the field.

## Not done

- One photo at a time; no several pages, no drawing on the photo to say which part to read.
- A photo is not shown on the board or kept in the conversation: only its text is. A later version could show what
  was read beside the picture.
- Not tried on a real iPhone or Android camera, nor on a real webcam: the flow was checked with a synthetic webcam in
  Chromium, and the phone path (capture input) in unit tests only. HEIC from an iPhone's gallery is converted by
  Safari or by the server's decoder only if it can read it.
- The tutor's prompt does not mention the `[incertain: …]` marks: the model reads them well enough, and the student has
  already seen and corrected them. Teaching the tutor about them would move the cached prompt prefix.
