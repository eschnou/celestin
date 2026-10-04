/** The settings screen (spec 010 R1): a title and the registered sections. It knows
 *  nothing about what a section holds. */

import { Link, useRouter } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { AuthPage } from "@/components/celestin/app-bar";
import { homePath, type User } from "@/lib/auth";
import { m } from "@/paraglide/messages";
import { panel, secondary } from "../styles";
import { SECTIONS, type SettingsSection } from "./sections";

export function SettingsPage({
  user,
  sections = SECTIONS,
}: {
  user: User;
  sections?: SettingsSection[];
}) {
  const router = useRouter();
  const back = (
    <>
      <ArrowLeft className="size-4" aria-hidden /> {m.settings_back()}
    </>
  );
  return (
    <AuthPage user={user}>
      <div className="flex flex-wrap items-center gap-3">
        {router.history.canGoBack() ? (
          <button type="button" onClick={() => router.history.back()} className={secondary}>
            {back}
          </button>
        ) : (
          <Link to={homePath(user)} className={secondary}>
            {back}
          </Link>
        )}
        <h1 className="text-xl font-bold">{m.settings_title()}</h1>
      </div>
      <div className="mt-6 grid gap-4">
        {sections
          .filter(({ roles }) => !roles || roles.includes(user.role))
          .map(({ id, title, Component }) => (
            <section key={id} aria-labelledby={`settings-${id}`} className={panel}>
              <h2 id={`settings-${id}`} className="text-base font-bold">
                {title()}
              </h2>
              <Component user={user} />
            </section>
          ))}
      </div>
    </AuthPage>
  );
}
