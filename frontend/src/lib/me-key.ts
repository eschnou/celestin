/** The query key of the signed-in user. Its own module so `i18n.ts` can watch the
 *  cache without importing `auth.ts`, which will import `i18n.ts` back. */
export const ME_QUERY_KEY = ["me"] as const;
