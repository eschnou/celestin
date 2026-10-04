// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoginForm, RegisterForm } from "@/components/celestin/auth-forms";
import { AuthError } from "@/lib/auth";
import { passwordRule } from "@/lib/password-rule";
import { withLocale } from "@/test/locale";

vi.mock("@/lib/auth", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/auth")>();
  return { ...mod, login: vi.fn(), register: vi.fn() };
});

import { login, register } from "@/lib/auth";

const USER = {
  id: "u1",
  email: "lea@example.be",
  name: "Léa",
  role: "student" as const,
  locale: "fr" as const,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LoginForm", () => {
  it("validates before calling the API", async () => {
    const onSuccess = vi.fn();
    render(<LoginForm onSuccess={onSuccess} />);
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    await screen.findByText("Indique ton adresse email.");
    expect(login).not.toHaveBeenCalled();
  });

  it("signs in and hands the user back", async () => {
    vi.mocked(login).mockResolvedValue(USER);
    const onSuccess = vi.fn();
    render(<LoginForm onSuccess={onSuccess} />);
    fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
    fireEvent.input(screen.getByLabelText("Mot de passe"), {
      target: { value: "mot-de-passe-solide" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(USER));
    expect(login).toHaveBeenCalledWith("lea@example.be", "mot-de-passe-solide");
  });

  it("shows the server's message under the form", async () => {
    vi.mocked(login).mockRejectedValue(
      new AuthError("invalid_credentials", "Email ou mot de passe incorrect."),
    );
    render(<LoginForm onSuccess={vi.fn()} />);
    fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
    fireEvent.input(screen.getByLabelText("Mot de passe"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Email ou mot de passe incorrect.",
    );
  });
});

describe("RegisterForm", () => {
  it("states the password rule and enforces the length", async () => {
    render(<RegisterForm onSuccess={vi.fn()} />);
    expect(screen.getByText(passwordRule())).toBeTruthy();
    fireEvent.input(screen.getByLabelText("Prénom"), { target: { value: "Léa" } });
    fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
    fireEvent.input(screen.getByLabelText("Mot de passe"), { target: { value: "court" } });
    fireEvent.click(screen.getByRole("button", { name: "Créer mon compte" }));
    await screen.findByText("Le mot de passe doit faire au moins 6 caractères.");
    expect(register).not.toHaveBeenCalled();
  });

  it("registers and hands the user back", async () => {
    vi.mocked(register).mockResolvedValue({ status: "signed_in", user: USER });
    const onSuccess = vi.fn();
    render(<RegisterForm onSuccess={onSuccess} />);
    fireEvent.input(screen.getByLabelText("Prénom"), { target: { value: "Léa" } });
    fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
    fireEvent.input(screen.getByLabelText("Mot de passe"), {
      target: { value: "mot-de-passe-solide" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Créer mon compte" }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(USER));
    expect(register).toHaveBeenCalledWith("lea@example.be", "mot-de-passe-solide", "Léa");
  });
});

describe("RegisterForm in verification mode", () => {
  it("reports a pending account instead of signing in", async () => {
    vi.mocked(register).mockResolvedValue({ status: "pending", user: USER });
    const onSuccess = vi.fn();
    const onPending = vi.fn();
    render(<RegisterForm onSuccess={onSuccess} onPending={onPending} />);
    fireEvent.input(screen.getByLabelText("Prénom"), { target: { value: "Léa" } });
    fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
    fireEvent.input(screen.getByLabelText("Mot de passe"), {
      target: { value: "mot-de-passe-solide" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Créer mon compte" }));
    await waitFor(() => expect(onPending).toHaveBeenCalledWith(USER));
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("shows why an account cannot sign in yet", async () => {
    vi.mocked(login).mockRejectedValue(
      new AuthError("account_disabled", "Ton compte n'est pas activé.", 403),
    );
    render(<LoginForm onSuccess={vi.fn()} />);
    fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
    fireEvent.input(screen.getByLabelText("Mot de passe"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Ton compte n'est pas activé.",
    );
  });
});

describe("in English", () => {
  it("words the sign-in form and its validation in English", () =>
    withLocale("en", async () => {
      render(<LoginForm onSuccess={vi.fn()} />);
      expect(document.documentElement.lang).toBe("en");
      expect(screen.getByRole("form", { name: "Sign in" })).toBeTruthy();
      expect(screen.getByLabelText("Email")).toBeTruthy();
      expect(screen.getByLabelText("Password")).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
      await screen.findByText("Enter your email address.");
      expect(screen.getByText("Enter your password.")).toBeTruthy();
      expect(login).not.toHaveBeenCalled();
    }));

  it("rejects an address that does not look valid, in English", () =>
    withLocale("en", async () => {
      render(<LoginForm onSuccess={vi.fn()} />);
      fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea" } });
      fireEvent.input(screen.getByLabelText("Password"), { target: { value: "x" } });
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
      await screen.findByText("This address doesn't look valid.");
    }));

  it("shows the server's message as received, whatever the interface language", () =>
    withLocale("en", async () => {
      vi.mocked(login).mockRejectedValue(
        new AuthError("invalid_credentials", "Email ou mot de passe incorrect."),
      );
      render(<LoginForm onSuccess={vi.fn()} />);
      fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
      fireEvent.input(screen.getByLabelText("Password"), { target: { value: "x" } });
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
      expect((await screen.findByRole("alert")).textContent).toBe(
        "Email ou mot de passe incorrect.",
      );
    }));

  it("falls back to the English generic error when the failure carries no message", () =>
    withLocale("en", async () => {
      vi.mocked(login).mockRejectedValue(new Error("boom"));
      render(<LoginForm onSuccess={vi.fn()} />);
      fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
      fireEvent.input(screen.getByLabelText("Password"), { target: { value: "x" } });
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
      expect((await screen.findByRole("alert")).textContent).toBe(
        "Célestin can't be reached right now. Try again in a moment.",
      );
    }));

  it("words the registration form, the password rule and its validation in English", () =>
    withLocale("en", async () => {
      render(<RegisterForm onSuccess={vi.fn()} />);
      expect(screen.getByRole("form", { name: "Registration" })).toBeTruthy();
      expect(
        screen.getByText("At least 6 characters. Not your first name or your email address."),
      ).toBeTruthy();
      fireEvent.input(screen.getByLabelText("First name"), { target: { value: "Lea" } });
      fireEvent.input(screen.getByLabelText("Email"), { target: { value: "lea@example.be" } });
      fireEvent.input(screen.getByLabelText("Password"), { target: { value: "short" } });
      fireEvent.click(screen.getByRole("button", { name: "Create my account" }));
      await screen.findByText("Your password must be at least 6 characters long.");
      expect(register).not.toHaveBeenCalled();
    }));
});
