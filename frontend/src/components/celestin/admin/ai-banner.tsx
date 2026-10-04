/** Shown on the administrator's dashboard while no AI provider is configured (specs 013 R7.5, 014 R12.3). */

import { Link } from "@tanstack/react-router";
import { useHealth } from "@/lib/tutor/health";
import { m } from "@/paraglide/messages";
import { warningBox } from "../styles";

export function AiBanner() {
  const health = useHealth();
  if (health.data?.aiConfigured !== false) return null;
  return (
    <p role="status" className={`mt-4 ${warningBox}`}>
      {m.admin_ai_banner()}{" "}
      <Link to="/settings" className="font-semibold text-primary hover:underline">
        {m.admin_ai_banner_link()}
      </Link>
    </p>
  );
}
