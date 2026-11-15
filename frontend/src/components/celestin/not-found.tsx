/** What a page shows when the API says no: the card of a course or chapter page that cannot
 *  be shown (005 R6.2), and the line of a read that failed, with « Réessayer ». */

import { Link } from "@tanstack/react-router";
import { m } from "@/paraglide/messages";

/** The failure in a sentence, then « Réessayer »: phrasing, inside the caller's paragraph. */
export function ErrorRetry({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <>
      {message}{" "}
      <button type="button" className="underline" onClick={onRetry}>
        {m.error_retry()}
      </button>
    </>
  );
}

export function NotFoundCard({ status }: { status: number }) {
  return (
    <div className="mt-6 rounded-xl border border-border bg-background p-6 text-center shadow-sheet">
      <h1 className="text-lg font-bold">
        {status === 404 ? m.error_page_not_found_title() : m.error_page_failed_title()}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {status === 404 ? m.error_card_not_found_hint() : m.error_retry_later()}
      </p>
      <Link
        to="/courses"
        className="mt-4 inline-block text-sm font-semibold text-primary hover:underline"
      >
        {m.nav_my_courses()}
      </Link>
    </div>
  );
}
