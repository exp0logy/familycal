# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies first (layer-cacheable)
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY . .

# Accept build-time VITE_* vars from docker-compose (passed as build args).
# Vite bakes these into the bundle at build time — they must be ARG+ENV here.
ARG VITE_API_BASE=/api
ARG VITE_WS_BASE=/ws
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_WS_BASE=${VITE_WS_BASE}

RUN npm run build

# ── Stage 2: serve ──────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Copy the Vite dist output
COPY --from=builder /app/dist /usr/share/nginx/html

# Drop the default nginx config; use ours
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

EXPOSE 80

# nginx runs as PID 1; use daemon off so Docker can manage the process
CMD ["nginx", "-g", "daemon off;"]
