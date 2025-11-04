# Multi-stage build for the Viewer app

FROM node:22-alpine AS build
WORKDIR /app

# Install dependencies first (better layer caching)
COPY viewer/package.json viewer/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Copy source
COPY viewer/. .

# Build static assets (and ensure config/plugins are available at runtime)
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

# Copy the built app and node_modules (vite preview needs vite and plugins)
COPY --from=build /app /app

# Create writable directories for logs and output; use existing 'node' user
RUN mkdir -p /logs /output \
    && chown -R node:node /app /logs /output

USER node

EXPOSE 5173

# Run vite preview with host binding so it is reachable in Kubernetes
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0"]
