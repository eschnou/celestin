/** Re-renders everything below it from scratch when the interface language changes
 *  (spec 010 §5.2): message functions read the language when they are called, so
 *  memoised output and pure helpers only follow a remount. Used by the root route and
 *  by the test harness, so both behave the same. */

import { Fragment, type ReactNode } from "react";
import { useLocale } from "@/lib/i18n";

export function LocaleBoundary({ children }: { children: ReactNode }) {
  return <Fragment key={useLocale()}>{children}</Fragment>;
}
