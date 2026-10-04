/** The password policy the forms state (the server enforces it; 004 R1). */
import { m } from "@/paraglide/messages";

export const PASSWORD_MIN = 6;

/** The sentence under the password field, in the interface language (read in render). */
export const passwordRule = (): string => m.auth_password_rule({ min: PASSWORD_MIN });
