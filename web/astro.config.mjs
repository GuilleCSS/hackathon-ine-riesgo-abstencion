import { defineConfig } from "astro/config";
import react from "@astrojs/react";

export default defineConfig({
  integrations: [react()],
  // CSS siempre en archivos: la CSP de la API sólo permite estilos en línea con hash.
  build: { inlineStylesheets: "never" },
  devToolbar: { enabled: false },
  vite: {
    server: {
      // En desarrollo (pnpm dev dentro de compose) la API es el servicio "api".
      proxy: { "/api": "http://api:8000", "/tiles": "http://api:8000" },
    },
  },
});
