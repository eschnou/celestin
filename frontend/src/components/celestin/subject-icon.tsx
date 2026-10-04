import { FlaskConical, Globe, Languages, Sigma, type LucideIcon } from "lucide-react";

import type { SubjectId } from "@/lib/tutor/types";

/** A subject's mark: one icon each, in the one accent colour of the product. */
const ICONS: Record<SubjectId, LucideIcon> = {
  mathematics: Sigma,
  sciences: FlaskConical,
  languages: Languages,
  general: Globe,
};

export function SubjectIcon({ subject, className }: { subject: SubjectId; className?: string }) {
  const Icon = ICONS[subject];
  return <Icon className={className} aria-hidden />;
}
