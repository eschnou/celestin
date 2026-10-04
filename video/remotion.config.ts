import { Config } from "@remotion/cli/config";
import { enableTailwind } from "@remotion/tailwind-v4";
import path from "node:path";

/**
 * The video renders the product's own React components: the whiteboard, its charts,
 * figures, plots and flowcharts, the tutor's messages. They live in ../frontend, so the
 * bundler resolves `@/…` there, shares one copy of React, and runs the frontend's
 * Tailwind design system (src/styles.css) unchanged.
 */
const frontend = path.resolve(process.cwd(), "../frontend");

Config.setVideoImageFormat("png");
Config.overrideWebpackConfig((current) => {
  const config = enableTailwind(current);
  return {
    ...config,
    resolve: {
      ...config.resolve,
      alias: {
        ...(config.resolve?.alias as Record<string, string> | undefined),
        "@": path.join(frontend, "src"),
        "@tanstack/react-router": path.resolve(process.cwd(), "src/stubs/router.tsx"),
        react: path.resolve(process.cwd(), "node_modules/react"),
        "react-dom": path.resolve(process.cwd(), "node_modules/react-dom"),
      },
      modules: [...(config.resolve?.modules ?? ["node_modules"]), path.join(frontend, "node_modules")],
    },
  };
});
