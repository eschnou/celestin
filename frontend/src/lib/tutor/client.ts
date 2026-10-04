/** Transport for one turn: POST the transcript, yield typed events. */

import { m } from "@/paraglide/messages";
import { parseChunk } from "./sse";
import type { HistoryEntry, LessonScope, TutorEvent } from "./types";

export const CHAT_URL = "/api/chat";

/** The message for a failure that carries none of its own, in the interface language
 *  (read when the error is made, never at import). */
export const genericError = (): string => m.error_generic();

/** One reason a pack or a path was refused (005 design 5): where, and why. */
export type ContentIssue = { where: string; message: string };

/** Any non-2xx answer from `/api`: the server's message (already in the user's language), its code, the
 *  status, and for a refused edit the issues that name what to fix. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 0,
    readonly issues: ContentIssue[] = [],
  ) {
    super(message);
  }
}

/** The server's message for a refused request, or `fallback` for anything else. */
export function apiMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** The HTTP status of a refused request; a network or unknown failure counts as 500. */
export function apiStatus(error: unknown): number {
  return error instanceof ApiError ? error.status : 500;
}

let onUnauthorized: (() => void) | null = null;

/** Registered once by the router: a 401 from any `/api` call must drop the
 *  cached identity, or the authenticated guard keeps waving a dead session through. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

async function ensureOk(response: Response): Promise<Response> {
  if (response.status === 401) onUnauthorized?.();
  if (!response.ok) {
    const { code, message, issues } = await readError(response);
    throw new ApiError(code, message, response.status, issues);
  }
  return response;
}

export async function getJson<T>(url: string): Promise<T> {
  return (await (await ensureOk(await fetch(url))).json()) as T;
}

/** POST (or PUT, PATCH, DELETE) a JSON body; cookies travel by default on the same origin. */
export async function sendJson(
  url: string,
  body?: unknown,
  init: { method?: "POST" | "PUT" | "PATCH" | "DELETE"; signal?: AbortSignal } = {},
): Promise<Response> {
  return ensureOk(
    await fetch(url, {
      method: init.method ?? "POST",
      headers: body === undefined ? {} : { "content-type": "application/json" },
      body: body === undefined ? null : JSON.stringify(body),
      signal: init.signal ?? null,
    }),
  );
}

/** POST (or PUT) a multipart form; the browser sets the content type and its boundary. */
export async function sendForm(
  url: string,
  form: FormData,
  method: "POST" | "PUT" = "POST",
  signal?: AbortSignal,
): Promise<Response> {
  return ensureOk(await fetch(url, { method, body: form, signal: signal ?? null }));
}

/**
 * A pre-stream failure arrives as JSON, not as SSE.
 *
 * Our own errors carry `{code, message}`, the message already in the user's language. A request the
 * framework rejects carries `{detail: [...]}` instead, and reading only `message`
 * there disguised a validation failure as "Célestin is unreachable" — sending the
 * learner to retry something that could never succeed.
 */
export async function readError(
  response: Response,
): Promise<{ code: string; message: string; issues: ContentIssue[] }> {
  const body = await response.json().catch(() => null);
  if (body && typeof body === "object") {
    const { code, message, detail, issues } = body as {
      code?: string;
      message?: string;
      detail?: unknown;
      issues?: unknown;
    };
    if (typeof message === "string")
      return {
        code: code ?? "http_error",
        message,
        issues: Array.isArray(issues) ? (issues as ContentIssue[]) : [],
      };
    if (detail !== undefined) {
      return {
        code: "invalid_request",
        message: m.error_invalid_request(),
        issues: [],
      };
    }
  }
  return { code: "http_error", message: genericError(), issues: [] };
}

function asEvent(name: string, data: string): TutorEvent | null {
  try {
    return { event: name, ...JSON.parse(data) } as TutorEvent;
  } catch {
    return null;
  }
}

/** One turn as typed events, whichever route serves it: the parcours posts its
 *  transcript here, a discussion posts its message (007 §3.11). */
export async function* streamEvents(
  url: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<TutorEvent> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: signal ?? null,
    });
  } catch (error) {
    if (signal?.aborted) return;
    throw error;
  }

  if (!response.ok || !response.body) {
    const { code, message } = await readError(response);
    yield { event: "error", code, message };
    yield { event: "turn.end", reason: "end", usage: {} };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let carry = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const { frames, rest } = parseChunk(decoder.decode(value, { stream: true }), carry);
      carry = rest;
      for (const frame of frames) {
        const event = asEvent(frame.event, frame.data);
        if (event) yield event;
      }
    }
  } finally {
    // Awaited so an early `break` in the consumer releases the connection before
    // control returns to it, rather than a microtask later.
    await reader.cancel().catch(() => {});
  }
}

export function streamTurn(
  scope: LessonScope,
  history: HistoryEntry[],
  signal?: AbortSignal,
): AsyncGenerator<TutorEvent> {
  return streamEvents(
    CHAT_URL,
    { course_id: scope.courseId, chapter_id: scope.chapterId, history },
    signal,
  );
}
