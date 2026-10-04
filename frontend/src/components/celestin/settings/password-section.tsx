/** « Mot de passe » (spec 012): change your own password, on proof of the current one. */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { changePassword, type User } from "@/lib/auth";
import { PASSWORD_MIN, passwordRule } from "@/lib/password-rule";
import { apiMessage } from "@/lib/tutor/client";
import { m } from "@/paraglide/messages";
import { field, fieldError, label, muted, primary } from "../styles";

// A factory, called in render: a message read at import would freeze the language.
const makeSchema = () =>
  z.object({
    current: z.string().min(1, m.settings_password_current_required()),
    next: z
      .string()
      .min(PASSWORD_MIN, m.auth_password_too_short({ min: PASSWORD_MIN }))
      .max(200, m.auth_password_too_long()),
  });
type Values = z.infer<ReturnType<typeof makeSchema>>;

export function PasswordSection({ user: _user }: { user: User }) {
  const schema = useMemo(makeSchema, []);
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const [failure, setFailure] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const submit = form.handleSubmit(async (values) => {
    setFailure(null);
    setDone(false);
    try {
      await changePassword(values.current, values.next);
      form.reset();
      setDone(true);
    } catch (error) {
      setFailure(apiMessage(error, m.error_generic()));
    }
  });
  const { errors, isSubmitting } = form.formState;
  return (
    <form onSubmit={submit} noValidate className="mt-2 max-w-sm space-y-4">
      <p className={muted}>{m.settings_password_help()}</p>
      <div>
        <label className={label} htmlFor="password-current">
          {m.settings_password_current()}
        </label>
        <input
          id="password-current"
          type="password"
          autoComplete="current-password"
          className={field}
          {...form.register("current")}
        />
        {errors.current && <p className={fieldError}>{errors.current.message}</p>}
      </div>
      <div>
        <label className={label} htmlFor="password-new">
          {m.settings_password_new()}
        </label>
        <input
          id="password-new"
          type="password"
          autoComplete="new-password"
          aria-describedby="password-new-rule"
          className={field}
          {...form.register("next")}
        />
        <p id="password-new-rule" className="mt-1 text-xs text-muted-foreground">
          {passwordRule()}
        </p>
        {errors.next && <p className={fieldError}>{errors.next.message}</p>}
      </div>
      {failure && (
        <p
          role="alert"
          className="rounded-md border-l-4 border-destructive bg-destructive/10 px-3 py-2 text-sm"
        >
          {failure}
        </p>
      )}
      {done && (
        <p role="status" className="text-sm text-primary">
          {m.settings_password_done()}
        </p>
      )}
      <button type="submit" disabled={isSubmitting} className={primary}>
        {m.settings_password_save()}
      </button>
    </form>
  );
}
