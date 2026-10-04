/**
 * Sign-in and registration forms (004 R1). Pure components: the route pages
 * supply what happens on success, so the forms are testable without a router.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
import { z } from "zod";
import { AuthError, login, register, setupAdmin, type User } from "@/lib/auth";
import { PASSWORD_MIN, passwordRule } from "@/lib/password-rule";
import { genericError } from "@/lib/tutor/client";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { alertBox, field, fieldError as error, label } from "./styles";

// Schemas are factories, called in render: a message read at import would freeze
// the language of whichever request imported the module first.
const makeEmail = () =>
  z.string().trim().min(1, m.auth_email_required()).email(m.auth_email_invalid());

const makeLoginSchema = () =>
  z.object({
    email: makeEmail(),
    password: z.string().min(1, m.auth_password_required()),
  });
const makeRegisterSchema = () =>
  z.object({
    name: z.string().trim().min(1, m.auth_name_required()).max(80, m.auth_name_too_long()),
    email: makeEmail(),
    password: z
      .string()
      .min(PASSWORD_MIN, m.auth_password_too_short({ min: PASSWORD_MIN }))
      .max(200, m.auth_password_too_long()),
  });

type LoginValues = z.infer<ReturnType<typeof makeLoginSchema>>;
type RegisterValues = z.infer<ReturnType<typeof makeRegisterSchema>>;

const submitClass =
  "inline-flex w-full items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50";

function serverMessage(err: unknown): string {
  if (err instanceof AuthError) return err.message;
  return genericError();
}

export function LoginForm({ onSuccess }: { onSuccess: (user: User) => void }) {
  const schema = useMemo(makeLoginSchema, []);
  const form = useForm<LoginValues>({ resolver: zodResolver(schema) });
  const [serverError, setServerError] = useState<string | null>(null);
  const submit = form.handleSubmit(async (values) => {
    setServerError(null);
    try {
      onSuccess(await login(values.email, values.password));
    } catch (err) {
      setServerError(serverMessage(err));
    }
  });
  const { errors, isSubmitting } = form.formState;
  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-label={m.auth_login_form()}>
      <div>
        <label className={label} htmlFor="login-email">
          {m.auth_label_email()}
        </label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          className={field}
          {...form.register("email")}
        />
        {errors.email && <p className={error}>{errors.email.message}</p>}
      </div>
      <div>
        <label className={label} htmlFor="login-password">
          {m.auth_label_password()}
        </label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          className={field}
          {...form.register("password")}
        />
        {errors.password && <p className={error}>{errors.password.message}</p>}
      </div>
      <ServerError message={serverError} />
      <button type="submit" disabled={isSubmitting} className={submitClass}>
        {m.auth_sign_in()}
      </button>
    </form>
  );
}

/** The three fields of a new account: name, email, password. Registration and the first-run setup
 *  (spec 013) ask for the same thing, so they share these and the schema. */
function AccountFields({
  form,
  idPrefix,
}: {
  form: UseFormReturn<RegisterValues>;
  idPrefix: string;
}) {
  const { errors } = form.formState;
  return (
    <>
      <div>
        <label className={label} htmlFor={`${idPrefix}-name`}>
          {m.auth_label_name()}
        </label>
        <input
          id={`${idPrefix}-name`}
          autoComplete="given-name"
          className={field}
          {...form.register("name")}
        />
        {errors.name && <p className={error}>{errors.name.message}</p>}
      </div>
      <div>
        <label className={label} htmlFor={`${idPrefix}-email`}>
          {m.auth_label_email()}
        </label>
        <input
          id={`${idPrefix}-email`}
          type="email"
          autoComplete="email"
          className={field}
          {...form.register("email")}
        />
        {errors.email && <p className={error}>{errors.email.message}</p>}
      </div>
      <div>
        <label className={label} htmlFor={`${idPrefix}-password`}>
          {m.auth_label_password()}
        </label>
        <input
          id={`${idPrefix}-password`}
          type="password"
          autoComplete="new-password"
          aria-describedby={`${idPrefix}-password-rule`}
          className={field}
          {...form.register("password")}
        />
        <p
          id={`${idPrefix}-password-rule`}
          className={cn("mt-1 text-xs text-muted-foreground", errors.password && "hidden")}
        >
          {passwordRule()}
        </p>
        {errors.password && <p className={error}>{errors.password.message}</p>}
      </div>
    </>
  );
}

function ServerError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className={alertBox}>
      {message}
    </p>
  );
}

export function RegisterForm({
  onSuccess,
  onPending,
}: {
  onSuccess: (user: User) => void;
  /** Verification mode: the account exists but is not enabled, so nobody is signed in. */
  onPending?: (user: User) => void;
}) {
  const schema = useMemo(makeRegisterSchema, []);
  const form = useForm<RegisterValues>({ resolver: zodResolver(schema) });
  const [serverError, setServerError] = useState<string | null>(null);
  const submit = form.handleSubmit(async (values) => {
    setServerError(null);
    try {
      const registered = await register(values.email, values.password, values.name);
      if (registered.status === "pending") onPending?.(registered.user);
      else onSuccess(registered.user);
    } catch (err) {
      setServerError(serverMessage(err));
    }
  });
  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-label={m.auth_register_form()}>
      <AccountFields form={form} idPrefix="register" />
      <ServerError message={serverError} />
      <button type="submit" disabled={form.formState.isSubmitting} className={submitClass}>
        {m.auth_create_account()}
      </button>
    </form>
  );
}

/** The first administrator of a fresh instance (spec 013): the registration fields, another button. */
export function SetupForm({ onSuccess }: { onSuccess: (user: User) => void }) {
  const schema = useMemo(makeRegisterSchema, []);
  const form = useForm<RegisterValues>({ resolver: zodResolver(schema) });
  const [serverError, setServerError] = useState<string | null>(null);
  const submit = form.handleSubmit(async (values) => {
    setServerError(null);
    try {
      onSuccess(await setupAdmin(values.email, values.password, values.name));
    } catch (err) {
      setServerError(serverMessage(err));
    }
  });
  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-label={m.setup_form()}>
      <AccountFields form={form} idPrefix="setup" />
      <ServerError message={serverError} />
      <button type="submit" disabled={form.formState.isSubmitting} className={submitClass}>
        {m.setup_submit()}
      </button>
    </form>
  );
}
