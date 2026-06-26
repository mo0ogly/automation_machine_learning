# automation_machine_learning — frontend image (React/Vite build served by nginx).
#
#   docker build -t automation-machine-learning-frontend ./frontend
#
# Two stages: node builds the static bundle, nginx serves it on :5173 with an SPA
# fallback. The browser calls the backend directly (VITE_API_URL, default
# http://localhost:8000) — both ports are published to the host by compose, so no
# reverse proxy is needed for the local-compose case. Override VITE_API_URL at
# build time to point a remote deployment at another host.

FROM node:22-alpine AS build
WORKDIR /app

# Baked into the bundle at build time (Vite inlines import.meta.env.VITE_*).
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

# Lockfile first for layer caching, then a reproducible install.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── runtime: static files on nginx ──────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=3s --retries=6 --start-period=5s \
    CMD wget -qO- http://localhost:5173/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
