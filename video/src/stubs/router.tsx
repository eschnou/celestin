import React from "react";

/** The video has no router: a link is just an anchor. */
export const Link: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement> & Record<string, unknown>> = ({
  children,
  className,
}) => <a className={className as string}>{children as React.ReactNode}</a>;
