/** The bar above the course pages and the page shell around them (004 §3.12, 005). */

import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import celestinMark from "@/assets/celestin-mark.svg";
import { UserMenu } from "@/components/celestin/user-menu";
import { homePath, type User } from "@/lib/auth";
import { APP_NAME } from "@/lib/brand";

export function AppBar({ user }: { user: User }) {
  return (
    <header className="flex items-center gap-3 border-b border-border bg-background px-4 py-3">
      <Link to={homePath(user)} className="flex items-center gap-2">
        <img src={celestinMark} alt="" className="size-8" />
        <span className="text-sm font-bold">{APP_NAME}</span>
      </Link>
      <UserMenu user={user} className="ml-auto text-sm" />
    </header>
  );
}

/** Bar on top, one centred column below: every page outside the lesson. */
export function AuthPage({
  user,
  children,
  wide = false,
}: {
  user: User;
  children: ReactNode;
  /** A table needs more room than a form: the administrator's dashboard. */
  wide?: boolean;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <AppBar user={user} />
      <main className={`mx-auto w-full px-4 py-6 ${wide ? "max-w-6xl" : "max-w-3xl"}`}>
        {children}
      </main>
    </div>
  );
}
