/**
 * Server-Sent Events framing.
 *
 * Pure: a chunk plus whatever was left over from the previous one, in; complete
 * frames plus the new leftover, out. No I/O, so it is testable against fixtures.
 */

export type SseFrame = { event: string; data: string };

export type ParseResult = { frames: SseFrame[]; rest: string };

export function parseChunk(chunk: string, carry = ""): ParseResult {
  const buffer = carry + chunk;
  const blocks = buffer.split("\n\n");
  // The last piece is either empty (the buffer ended on a frame boundary) or a
  // partial frame still arriving; either way it carries over.
  const rest = blocks.pop() ?? "";
  const frames: SseFrame[] = [];

  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line === "" || line.startsWith(":")) continue; // blank or heartbeat comment
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length > 0) frames.push({ event, data: data.join("\n") });
  }

  return { frames, rest };
}
