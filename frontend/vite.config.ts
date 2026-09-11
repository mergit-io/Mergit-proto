import { defineConfig, type Plugin, type ViteDevServer, type PreviewServer } from "vite";
import type { IncomingMessage, ServerResponse } from "node:http";
import react from "@vitejs/plugin-react";

/* The landing page is a framed document with `sandbox` and no `allow-same-origin`,
   which gives it an opaque origin — so every asset it loads is a cross-origin
   request, and a still it draws into a canvas taints that canvas unless the
   response says otherwise. The card cloth uploads exactly such a canvas as a WebGL
   texture, and a tainted one throws. `/landing` is public marketing material, so
   it is served to anyone; the header is scoped to that prefix all the same.
   Production serves the same header from backend/main.py. */
function landingCors(): Plugin {
  return {
    name: "mergit-landing-cors",
    configureServer(server: ViteDevServer) {
      server.middlewares.use(headers);
    },
    configurePreviewServer(server: PreviewServer) {
      server.middlewares.use(headers);
    },
  };
}

function headers(req: IncomingMessage, res: ServerResponse, next: () => void) {
  if (req.url && req.url.startsWith("/landing/")) {
    res.setHeader("Access-Control-Allow-Origin", "*");
  }
  next();
}

export default defineConfig({
  plugins: [react(), landingCors()],
  server: {
    port: 3000,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
