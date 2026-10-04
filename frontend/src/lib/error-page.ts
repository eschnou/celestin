import { languageHeaders } from "./html-headers";
import { DEFAULT_LOCALE, parseAcceptLanguage, type Locale } from "./locale";

/** The page the server answers when rendering itself failed, so it can lean on no
 *  catalog, no router and no framework: its two languages are written out here
 *  (spec 010 §5.6). */
const TEXT: Record<Locale, { title: string; body: string; retry: string; home: string }> = {
  fr: {
    title: "Cette page ne s'est pas chargée",
    body: "Un problème est survenu de notre côté. Tu peux actualiser la page ou revenir à l'accueil.",
    retry: "Réessayer",
    home: "Retour à l'accueil",
  },
  en: {
    title: "This page didn't load",
    body: "Something went wrong on our end. You can try refreshing or head back home.",
    retry: "Try again",
    home: "Go home",
  },
};

/** The 500 answer for a render that failed: the page in the language of the request's header
 *  (nothing else is known here), marked as language-dependent for the caches. */
export function errorResponse(request: Request): Response {
  const locale = parseAcceptLanguage(request.headers.get("accept-language"));
  return languageHeaders(
    new Response(renderErrorPage(locale), {
      status: 500,
      headers: { "content-type": "text/html; charset=utf-8" },
    }),
  );
}

export function renderErrorPage(locale: Locale = DEFAULT_LOCALE): string {
  const text = TEXT[locale];
  return `<!doctype html>
<html lang="${locale}">
  <head>
    <meta charset="utf-8" />
    <title>${text.title}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font: 15px/1.5 system-ui, -apple-system, sans-serif; background: #fafafa; color: #111; display: grid; place-items: center; min-height: 100vh; margin: 0; padding: 1.5rem; }
      .card { max-width: 28rem; width: 100%; text-align: center; padding: 2rem; }
      h1 { font-size: 1.25rem; margin: 0 0 0.5rem; }
      p { color: #4b5563; margin: 0 0 1.5rem; }
      .actions { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; }
      a, button { padding: 0.5rem 1rem; border-radius: 0.375rem; font: inherit; cursor: pointer; text-decoration: none; border: 1px solid transparent; }
      .primary { background: #111; color: #fff; }
      .secondary { background: #fff; color: #111; border-color: #d1d5db; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>${text.title}</h1>
      <p>${text.body}</p>
      <div class="actions">
        <button class="primary" onclick="location.reload()">${text.retry}</button>
        <a class="secondary" href="/">${text.home}</a>
      </div>
    </div>
  </body>
</html>`;
}
