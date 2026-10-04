/** What a user can change about their own account (spec 010 R1). One setting for now;
 *  a later one is a field here and a section on the settings screen. */

import { ME_URL, type User } from "./auth";
import type { Locale } from "./locale";
import { sendJson } from "./tutor/client";

export type Preferences = { locale?: Locale };

export async function updatePreferences(patch: Preferences): Promise<User> {
  const response = await sendJson(ME_URL, patch, { method: "PATCH" });
  return ((await response.json()) as { user: User }).user;
}
