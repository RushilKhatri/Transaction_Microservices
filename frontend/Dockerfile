# ── Frontend Dockerfile (multi-stage) ────────────────────────────────────────
# Stage 1: Build the Vite bundle
FROM node:18-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --silent

COPY . .
# Inject build-time env vars so Vite bakes service URLs into the bundle
ARG VITE_TRANSACTION_URL=http://localhost:5001
ARG VITE_FRAUD_URL=http://localhost:5002
ARG VITE_NOTIFICATION_URL=http://localhost:5003
ENV VITE_TRANSACTION_URL=$VITE_TRANSACTION_URL
ENV VITE_FRAUD_URL=$VITE_FRAUD_URL
ENV VITE_NOTIFICATION_URL=$VITE_NOTIFICATION_URL

RUN npm run build

# ── Stage 2: Serve with Nginx ─────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Copy build output
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
