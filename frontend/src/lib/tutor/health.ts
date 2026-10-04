/** Whether the backend offers voice (003 design 3.15) and dictation. Off until known. */

import { useQuery, type QueryClient } from "@tanstack/react-query";

export const HEALTH_URL = "/api/health";
export const HEALTH_KEY = ["health"] as const;

/** The health is cached for the life of the page: read it again when it may have changed (an AI provider was
 *  saved, the instance was just set up). */
export function invalidateHealth(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: HEALTH_KEY });
}

/** `aiConfigured`: an AI provider is configured (specs 013, 014). A backend that does not say is taken to be
 *  configured, so an older one never shows the missing-key banner. */
export type Health = { voice: boolean; dictation: boolean; aiConfigured: boolean };

export async function fetchHealth(): Promise<Health> {
  const response = await fetch(HEALTH_URL);
  if (!response.ok) throw new Error(`health: HTTP ${response.status}`);
  const body = (await response.json()) as {
    voice?: unknown;
    dictation?: unknown;
    ai_configured?: unknown;
  };
  return {
    voice: body.voice === true,
    dictation: body.dictation === true,
    aiConfigured: body.ai_configured !== false,
  };
}

export function useHealth() {
  return useQuery({
    queryKey: HEALTH_KEY,
    queryFn: fetchHealth,
    staleTime: Infinity,
    retry: 1,
  });
}
