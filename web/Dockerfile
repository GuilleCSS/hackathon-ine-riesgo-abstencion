# Node sólo para construir el sitio (Astro + React). En producción no corre Node:
# la API de Python sirve web/dist.
FROM node:24.22.1-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205

RUN npm install --global --ignore-scripts pnpm@12.13.0
# Sin telemetría de Astro.
ENV ASTRO_TELEMETRY_DISABLED=1
WORKDIR /web
