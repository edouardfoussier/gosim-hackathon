/**
 * Static-export variant of `next.config.ts`, swapped in by
 * `desktop/scripts/build-frontend.sh` for the duration of `pnpm build`
 * and restored to the dev config on exit.
 *
 * Differences vs. the live config:
 *
 * - `output: "export"`            — emits a static bundle to `app/out/`
 *   that Tauri's `frontendDist` field can serve via `tauri://localhost`.
 * - `images.unoptimized: true`    — disables Next's runtime image
 *   optimisation, which requires a Node.js server. Our panel uses
 *   lucide icons + CSS, so this is a no-op visually.
 * - `trailingSlash: true`         — produces `out/<route>/index.html`
 *   instead of `out/<route>.html`. Tauri's webview file-resolver
 *   handles both, but the directory style avoids a few corner-case
 *   redirects on case-insensitive macOS file systems.
 *
 * Everything else mirrors the dev config so the production bundle's
 * runtime semantics match `pnpm dev` as closely as possible.
 */

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
