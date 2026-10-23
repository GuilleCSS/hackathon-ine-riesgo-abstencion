import { defineConfig } from "astro/config";
import react from "@astrojs/react";

export default defineConfig({
  integrations: [react()],
  // CSS siempre en archivos: la CSP de la API sólo permite estilos en línea con hash.
  build: { inlineStylesheets: "never" },
  devToolbar: { enabled: false },
  vite: {
    server: {
      // En desarrollo (pnpm dev) /api y /tiles van a la API. compose define API_URL=http://api:8000.
      proxy: {
        "/api": process.env.API_URL ?? "http://localhost:8000",
        "/tiles": process.env.API_URL ?? "http://localhost:8000",
      },
    },
  },
});
