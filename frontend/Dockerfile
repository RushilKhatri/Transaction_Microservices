# ── Frontend Dockerfile (multi-stage) ────────────────────────────────────────
# Stage 1: Build the Vite bundle
FROM node:18-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --include=dev --silent

COPY . .
# Inject build-time env vars so Vite bakes the API prefix into the bundle
ARG VITE_API_PREFIX=/api
ENV VITE_API_PREFIX=$VITE_API_PREFIX

RUN npm run build

# ── Stage 2: Serve with Nginx ─────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Copy build output
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
