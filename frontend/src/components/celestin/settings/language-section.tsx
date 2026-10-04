/** « Langue » (spec 010 R1.2, R1.5): the interface language, saved to the account. */

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { User } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";
import { ME_QUERY_KEY } from "@/lib/me-key";
import { AUTONYM, LOCALES, isLocale } from "@/lib/locale";
import { updatePreferences } from "@/lib/settings";
import { m } from "@/paraglide/messages";
import { setLocale } from "@/paraglide/runtime";
import { muted } from "../styles";

export function LanguageSection({ user: _user }: { user: User }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const current = useLocale();
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  async function choose(value: string) {
    if (!isLocale(value) || value === current) return;
    setSaving(true);
    setFailed(false);
    try {
      // The account first: if saving fails, the interface stays as it was.
      await updatePreferences({ locale: value });
      setLocale(value, { reload: false });
      // The server wrote subject labels, chapter numbers, failure messages and markers in the
      // old language, and some of it is cached for good: refetch it when next shown.
      await queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== ME_QUERY_KEY[0] });
      // Page titles come from each route's head(): run them again.
      await router.invalidate();
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-2">
      <p className={muted}>{m.settings_language_help()}</p>
      <RadioGroup
        value={current}
        onValueChange={(value) => void choose(value)}
        disabled={saving}
        aria-label={m.settings_language_title()}
        aria-busy={saving}
        className="mt-3"
      >
        {LOCALES.map((locale) => (
          <div key={locale} className="flex items-center gap-2">
            <RadioGroupItem value={locale} id={`language-${locale}`} />
            <Label htmlFor={`language-${locale}`} lang={locale} className="cursor-pointer text-sm">
              {AUTONYM[locale]}
            </Label>
          </div>
        ))}
      </RadioGroup>
      {failed && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {m.settings_language_error()}
        </p>
      )}
    </div>
  );
}
