import { createFileRoute, redirect } from "@tanstack/react-router";

/** The lesson lives under a course and a chapter (005 R10.1). */
export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/courses" });
  },
});
