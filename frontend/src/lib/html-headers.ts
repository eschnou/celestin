/** A page whose text depends on the request's Accept-Language must not be served to
 *  anyone else from a shared cache. Amplify's CloudFront honours the app's
 *  Cache-Control and has no Accept-Language in its cache key, so `Vary` alone is not
 *  enough (spec 010 §5.2). Only HTML: assets keep their own headers. */
export function languageHeaders(response: Response): Response {
  if (!response.headers.get("content-type")?.includes("text/html")) return response;
  try {
    mark(response.headers);
    return response;
  } catch {
    // Immutable headers (a response that came from fetch): copy.
    const headers = new Headers(response.headers);
    mark(headers);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  }
}

function mark(headers: Headers): void {
  headers.append("vary", "Accept-Language");
  headers.set("cache-control", "private, no-cache");
}
