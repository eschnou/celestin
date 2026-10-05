/** « Précédent / Suivant » with a line saying where the reader is. */

import { m } from "@/paraglide/messages";
import { muted, secondary } from "./styles";

export function Pager({
  label,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
}: {
  label: string;
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <nav className="mt-4 flex items-center justify-between gap-3">
      <span className={muted}>{label}</span>
      <span className="flex gap-2">
        <button type="button" className={secondary} disabled={!hasPrev} onClick={onPrev}>
          {m.admin_prev()}
        </button>
        <button type="button" className={secondary} disabled={!hasNext} onClick={onNext}>
          {m.admin_next()}
        </button>
      </span>
    </nav>
  );
}
