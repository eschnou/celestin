/** The administrator's list of accounts (spec 012): filter, search, enable or disable one, reset
 *  a password. The table shows what the server says and nothing else: a click is a request, and
 *  the row changes when the answer comes back. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, UserCheck, UserX } from "lucide-react";
import { useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/celestin/confirm-dialog";
import { field, muted, panel, secondary } from "@/components/celestin/styles";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ADMIN_USERS_KEY,
  adminUsersQuery,
  PAGE_SIZE,
  resetUserPassword,
  setUserEnabled,
  type AdminUser,
  type UserStatus,
} from "@/lib/admin";
import type { RegistrationMode, Role, User } from "@/lib/auth";
import { formatCount, formatDate } from "@/lib/i18n-format";
import { apiMessage } from "@/lib/tutor/client";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

// Tables of message functions, never called at import (the language is the request's).
const ROLE_LABEL: Record<Role, () => string> = {
  student: m.admin_role_student,
  parent: m.admin_role_parent,
  admin: m.admin_role_admin,
};
const MODE_LABEL: Record<RegistrationMode, () => string> = {
  open: m.admin_mode_open,
  closed: m.admin_mode_closed,
  verification: m.admin_mode_verification,
};

export function UsersPanel({ me }: { me: User }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<UserStatus>("all");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [revealed, setRevealed] = useState<{ user: AdminUser; password: string } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  // The search waits for a pause in the typing, and starts again from the first page.
  useEffect(() => {
    if (search === q) return; // nothing typed: not on mount, and not after the debounce itself
    const id = setTimeout(() => {
      setQ(search);
      setOffset(0);
    }, 250);
    return () => clearTimeout(id);
  }, [search, q]);

  const list = useQuery(adminUsersQuery({ q, status, offset }));
  const refresh = () => queryClient.invalidateQueries({ queryKey: ADMIN_USERS_KEY });

  const toggle = useMutation({
    mutationFn: ({ user, enabled }: { user: AdminUser; enabled: boolean }) =>
      setUserEnabled(user.id, enabled),
    onMutate: () => setFailure(null),
    onSuccess: refresh,
    onError: (error) => setFailure(apiMessage(error, m.error_generic())),
  });
  const reset = useMutation({
    mutationFn: (user: AdminUser) => resetUserPassword(user.id),
    onMutate: () => setFailure(null),
    onSuccess: (answer) => {
      setRevealed(answer);
      void refresh();
    },
    onError: (error) => setFailure(apiMessage(error, m.error_generic())),
  });

  const data = list.data;
  // Enabling the last row of a page can leave the offset past the end, and the pager is hidden
  // when everything fits on one page: step back to the last page that exists.
  const total = data?.total;
  useEffect(() => {
    if (total === undefined || list.isPlaceholderData || offset === 0 || offset < total) return;
    setOffset(Math.max(0, Math.floor((total - 1) / PAGE_SIZE) * PAGE_SIZE));
  }, [total, offset, list.isPlaceholderData]);
  const filters: { id: UserStatus; label: string }[] = data
    ? [
        { id: "all", label: m.admin_filter_all({ count: formatCount(data.counts.total) }) },
        {
          id: "disabled",
          label: m.admin_filter_disabled({ count: formatCount(data.counts.disabled) }),
        },
        {
          id: "enabled",
          label: m.admin_filter_enabled({ count: formatCount(data.counts.enabled) }),
        },
      ]
    : [];

  return (
    <div className="mt-6 grid gap-4">
      {data && (
        <section className={panel} aria-labelledby="admin-mode">
          <h2 id="admin-mode" className="text-base font-bold">
            {m.admin_mode_label()}
          </h2>
          <p className="mt-1 text-sm">{MODE_LABEL[data.registration_mode]()}</p>
          <p className={cn(muted, "mt-1")}>{m.admin_mode_help()}</p>
        </section>
      )}

      <section className={panel} aria-label={m.admin_title()}>
        <div className="flex flex-wrap items-center gap-3">
          <div role="group" aria-label={m.admin_filter_label()} className="flex flex-wrap gap-1.5">
            {filters.map((filter) => (
              <button
                key={filter.id}
                type="button"
                aria-pressed={status === filter.id}
                onClick={() => {
                  setStatus(filter.id);
                  setOffset(0);
                }}
                className={cn(
                  secondary,
                  status === filter.id && "border-primary bg-primary/10 text-primary",
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label={m.admin_search_label()}
            placeholder={m.admin_search_label()}
            maxLength={100}
            className={cn(field, "ml-auto w-full sm:w-72")}
          />
        </div>

        {failure && (
          <p
            role="alert"
            className="mt-3 rounded-md border-l-4 border-destructive bg-destructive/10 px-3 py-2 text-sm"
          >
            {failure}
          </p>
        )}

        {list.isError && !data ? (
          <p role="alert" className="mt-4 text-sm text-destructive">
            {m.admin_load_failed()}
          </p>
        ) : (
          <div className={cn("mt-4 overflow-x-auto", list.isPlaceholderData && "opacity-60")}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{m.admin_col_name()}</TableHead>
                  <TableHead>{m.admin_col_email()}</TableHead>
                  <TableHead>{m.admin_col_role()}</TableHead>
                  <TableHead>{m.admin_col_status()}</TableHead>
                  <TableHead>{m.admin_col_created()}</TableHead>
                  <TableHead>{m.admin_col_seen()}</TableHead>
                  <TableHead className="text-right">{m.admin_col_actions()}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.users.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    isMe={user.id === me.id}
                    busy={toggle.isPending || reset.isPending}
                    onToggle={(enabled) => toggle.mutate({ user, enabled })}
                    onReset={() => reset.mutate(user)}
                  />
                ))}
              </TableBody>
            </Table>
            {data && data.users.length === 0 && (
              <p className={cn(muted, "py-6 text-center")}>{m.admin_empty()}</p>
            )}
          </div>
        )}

        {data && data.total > PAGE_SIZE && (
          <nav className="mt-4 flex items-center justify-between gap-3">
            <span className={muted}>
              {m.admin_range({
                from: formatCount(offset + 1),
                to: formatCount(Math.min(offset + PAGE_SIZE, data.total)),
                total: formatCount(data.total),
              })}
            </span>
            <span className="flex gap-2">
              <button
                type="button"
                className={secondary}
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                {m.admin_prev()}
              </button>
              <button
                type="button"
                className={secondary}
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                {m.admin_next()}
              </button>
            </span>
          </nav>
        )}
      </section>

      <PasswordDialog revealed={revealed} onClose={() => setRevealed(null)} />
    </div>
  );
}

function UserRow({
  user,
  isMe,
  busy,
  onToggle,
  onReset,
}: {
  user: AdminUser;
  isMe: boolean;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onReset: () => void;
}) {
  const name = user.name;
  return (
    <TableRow>
      <TableCell className="font-medium">
        {name} {isMe && <span className="font-normal text-muted-foreground">{m.admin_you()}</span>}
      </TableCell>
      <TableCell className="break-all">{user.email}</TableCell>
      <TableCell>{ROLE_LABEL[user.role]()}</TableCell>
      <TableCell>
        <Badge variant={user.enabled ? "secondary" : "destructive"}>
          {user.enabled ? m.admin_status_enabled() : m.admin_status_disabled()}
        </Badge>
      </TableCell>
      <TableCell className="whitespace-nowrap">{formatDate(user.created_at)}</TableCell>
      <TableCell className="whitespace-nowrap">
        {user.last_seen_at ? formatDate(user.last_seen_at) : m.admin_never()}
      </TableCell>
      <TableCell>
        {/* An admin cannot disable or reset themselves: the server refuses, so no button. */}
        {!isMe && (
          <div className="flex justify-end gap-2">
            {user.enabled ? (
              <ConfirmDialog
                destructive
                title={m.admin_disable_title({ name })}
                description={m.admin_disable_body()}
                confirm={m.admin_disable()}
                onConfirm={() => onToggle(false)}
                trigger={
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={m.admin_disable_label({ name })}
                    className={secondary}
                  >
                    <UserX className="size-4" aria-hidden /> {m.admin_disable()}
                  </button>
                }
              />
            ) : (
              <button
                type="button"
                disabled={busy}
                aria-label={m.admin_enable_label({ name })}
                onClick={() => onToggle(true)}
                className={secondary}
              >
                <UserCheck className="size-4" aria-hidden /> {m.admin_enable()}
              </button>
            )}
            <ConfirmDialog
              title={m.admin_reset_title({ name })}
              description={m.admin_reset_body()}
              confirm={m.admin_reset_confirm()}
              onConfirm={onReset}
              trigger={
                <button
                  type="button"
                  disabled={busy}
                  aria-label={m.admin_reset_label({ name })}
                  className={secondary}
                >
                  <KeyRound className="size-4" aria-hidden /> {m.admin_reset_password()}
                </button>
              }
            />
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}

/** The temporary password, once. Closing the dialog forgets it. */
function PasswordDialog({
  revealed,
  onClose,
}: {
  revealed: { user: AdminUser; password: string } | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  useEffect(() => setCopied(false), [revealed]);

  async function copy() {
    if (!revealed) return;
    try {
      await navigator.clipboard.writeText(revealed.password);
      setCopied(true);
    } catch {
      // clipboard blocked: the password is selectable on screen
    }
  }

  return (
    <Dialog open={revealed !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        {revealed && (
          <>
            <DialogHeader>
              <DialogTitle>{m.admin_password_title({ name: revealed.user.name })}</DialogTitle>
              <DialogDescription>{m.admin_password_body()}</DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2">
              <code
                aria-label={m.admin_password_label()}
                className="flex-1 select-all break-all rounded-md border border-border bg-secondary px-3 py-2 font-mono text-sm"
              >
                {revealed.password}
              </code>
              <button type="button" onClick={() => void copy()} className={secondary}>
                {copied ? (
                  <Check className="size-4" aria-hidden />
                ) : (
                  <Copy className="size-4" aria-hidden />
                )}{" "}
                {copied ? m.admin_copied() : m.admin_copy()}
              </button>
            </div>
            <DialogFooter>
              <button type="button" onClick={onClose} className={secondary}>
                {m.admin_close()}
              </button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
