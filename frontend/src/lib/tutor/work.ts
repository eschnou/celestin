/**
 * Photographed work (the camera in the composer): a photo of the student's handwriting goes to the server,
 * a vision model reads it into text, and the text lands in the message field for her to correct. The photo
 * itself is neither kept nor shown to Célestin.
 */

import { sendForm } from "@/lib/tutor/client";

export const workUrl = (courseId: string): string =>
  `/api/courses/${encodeURIComponent(courseId)}/work`;

/** The longest side sent. Enough to read a line of handwriting, a fraction of a phone's 12 megapixels. */
export const MAX_SIDE = 1800;
const QUALITY = 0.85;
/** A photo that is already this small and a JPEG goes as it is. */
const SEND_AS_IS_BYTES = 1_500_000;

export async function readWork(
  courseId: string,
  photo: Blob,
  signal?: AbortSignal,
): Promise<string> {
  const form = new FormData();
  form.append("photo", photo, photo.type === "image/png" ? "work.png" : "work.jpg");
  const response = await sendForm(workUrl(courseId), form, "POST", signal);
  const body = (await response.json()) as { text?: unknown };
  return typeof body.text === "string" ? body.text.trim() : "";
}

/**
 * The photo as it is worth sending: turned the right way up (a phone stores the way it was held in the file's
 * metadata), shrunk to `MAX_SIDE`, as a JPEG. Where the browser cannot do that (no `createImageBitmap`, a
 * format it cannot decode) the original goes, and the server, which does the same work, has the last word.
 */
export async function preparePhoto(file: Blob): Promise<Blob> {
  if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return file;
  }
  try {
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.type === "image/jpeg" && file.size <= SEND_AS_IS_BYTES) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) return file;
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", QUALITY),
    );
    return blob ?? file;
  } finally {
    bitmap.close();
  }
}
