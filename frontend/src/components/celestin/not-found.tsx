/** The card a course or chapter page shows when the API says no (005 R6.2). */

import { Link } from "@tanstack/react-router";
import { m } from "@/paraglide/messages";

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
