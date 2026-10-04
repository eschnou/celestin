/** Who is signed in, and what they can do about it: settings and sign-out (spec 010
 *  R1.1). One menu for the course pages' bar and the chapter bar. */

import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { ChevronDown, Ellipsis, LogOut, Settings, ShieldCheck } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSignOut, type User } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

/** `compact` is the small-screen form: a « ⋯ » button instead of the name, which the menu
 *  then shows as its first line, with the page's own entries (`children`) above the account's. */
export function UserMenu({
  user,
  className,
  compact = false,
  children,
}: {
  user: User;
  className?: string;
  compact?: boolean;
  children?: ReactNode;
}) {
  const signOut = useSignOut();
  return (
    <DropdownMenu>
      {compact ? (
        <DropdownMenuTrigger
          aria-label={m.nav_menu()}
          className={cn(
            "inline-flex size-10 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
            className,
          )}
        >
          <Ellipsis className="size-5" aria-hidden />
        </DropdownMenuTrigger>
      ) : (
        <DropdownMenuTrigger
          className={cn(
            "inline-flex min-w-0 items-center gap-1 rounded-md px-2 py-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
            className,
          )}
        >
          <span className="truncate">{user.name}</span>
          <ChevronDown className="size-3.5 shrink-0" aria-hidden />
        </DropdownMenuTrigger>
      )}
      <DropdownMenuContent align="end">
        {compact && (
          <>
            <DropdownMenuLabel className="font-normal text-muted-foreground">
              {user.name}
            </DropdownMenuLabel>
            {children}
            <DropdownMenuSeparator />
          </>
        )}
        {user.role === "admin" && (
          <DropdownMenuItem asChild>
            <Link to="/admin">
              <ShieldCheck /> {m.nav_admin()}
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem asChild>
          <Link to="/settings">
            <Settings /> {m.nav_settings()}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOut /> {m.nav_sign_out()}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
