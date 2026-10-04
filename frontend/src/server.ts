import "./lib/error-capture";

import { consumeLastCapturedError } from "./lib/error-capture";
import { errorResponse } from "./lib/error-page";
import { languageHeaders } from "./lib/html-headers";
import { registerLocaleStrategies } from "./lib/i18n";
import { paraglideMiddleware } from "./paraglide/server.js";

// Before the first request is read. By name: a bare import of ./lib/i18n would be tree-shaken away.
registerLocaleStrategies();

type ServerEntry = {
  fetch: (request: Request, env: unknown, ctx: unknown) => Promise<Response> | Response;
};

let serverEntryPromise: Promise<ServerEntry> | undefined;

async function getServerEntry(): Promise<ServerEntry> {
  if (!serverEntryPromise) {
    serverEntryPromise = import("@tanstack/react-start/server-entry").then(
      (m) => (m.default ?? m) as ServerEntry,
    );
  }
  return serverEntryPromise;
}

// h3 swallows in-handler throws into a normal 500 Response with body
// {"unhandled":true,"message":"HTTPError"} — try/catch alone never fires for those.
async function normalizeCatastrophicSsrResponse(
  response: Response,
  request: Request,
): Promise<Response> {
  if (response.status < 500) return response;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return response;

  const body = await response.clone().text();
  if (!isH3SwallowedErrorBody(body)) return response;

  console.error(consumeLastCapturedError() ?? new Error(`h3 swallowed SSR error: ${body}`));
  return errorResponse(request);
}

function isH3SwallowedErrorBody(body: string): boolean {
  try {
    const payload = JSON.parse(body) as { unhandled?: unknown; message?: unknown };
    return payload.unhandled === true && payload.message === "HTTPError";
  } catch {
    return false;
  }
}

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    try {
      const handler = await getServerEntry();
      // The request's language (AsyncLocalStorage) for the whole render. The original
      // request goes down: there is no URL strategy, so nothing to delocalize.
      const response = await paraglideMiddleware(request, () => handler.fetch(request, env, ctx));
      return await normalizeCatastrophicSsrResponse(languageHeaders(response), request);
    } catch (error) {
      console.error(error);
      return errorResponse(request);
    }
  },
};
