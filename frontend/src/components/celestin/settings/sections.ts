/** The sections of the settings screen, registered in one place (spec 010 NFR 4.1.9).
 *  A later setting (name, email address) is a component, its messages and an
 *  entry here: the shell, the menu and the language resolver do not change. */

import type { ComponentType } from "react";
import type { Role, User } from "@/lib/auth";
import { m } from "@/paraglide/messages";
import { AISection } from "./ai-section";
import { LanguageSection } from "./language-section";
import { PasswordSection } from "./password-section";

export type SettingsSection = {
  id: string;
  /** A function, never a string: a title read at import time would freeze the language. */
  title: () => string;
  Component: ComponentType<{ user: User }>;
  /** Who sees it. Everyone when absent. A convenience: the server refuses the others anyway. */
  roles?: Role[];
};

export const languageSection: SettingsSection = {
  id: "language",
  title: () => m.settings_language_title(),
  Component: LanguageSection,
};

export const passwordSection: SettingsSection = {
  id: "password",
  title: () => m.settings_password_title(),
  Component: PasswordSection,
};

/** The AI provider, its key and its models (specs 013, 014): the administrator's, nobody else's. */
export const aiSection: SettingsSection = {
  id: "ai",
  title: () => m.settings_ai_title(),
  Component: AISection,
  roles: ["admin"],
};

export const SECTIONS: SettingsSection[] = [languageSection, passwordSection, aiSection];
