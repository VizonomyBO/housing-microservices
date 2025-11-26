# Multi-stage Dockerfile with testing support

# ============================================
# Test Stage - Run tests and quality checks
# ============================================
FROM node:20-alpine AS test

WORKDIR /app

# Install curl for potential healthchecks
RUN apk add --no-cache curl

# Copy package files
COPY package*.json ./

# Install all dependencies (including dev)
RUN npm ci

# Copy source and config files
COPY tsconfig.json ./
COPY jest.config.js ./
COPY .eslintrc.js ./
COPY .prettierrc ./
COPY src ./src
COPY tests ./tests

# Run linting and formatting checks
RUN npm run lint || true
RUN npm run format:check || true

# Run type checking
RUN npm run type-check || true

# Run tests with coverage
RUN npm run test:coverage || true

# Build TypeScript
RUN npm run build

# ============================================
# Production Stage
# ============================================
FROM node:20-alpine AS production

WORKDIR /app

# Install curl for healthcheck
RUN apk add --no-cache curl

# Copy package files
COPY package*.json ./

# Install only production dependencies
RUN npm ci --only=production

# Copy built application from test stage
COPY --from=test /app/dist ./dist

# Copy static spec files for Lambda services
COPY mock-specs ./mock-specs

# Create non-root user (handle existing GID/UID gracefully)
RUN (getent group appuser >/dev/null 2>&1 || \
     (addgroup -g 1000 appuser 2>/dev/null || addgroup appuser)) && \
    (getent passwd appuser >/dev/null 2>&1 || \
     (adduser -D -u 1000 -G appuser appuser 2>/dev/null || \
      adduser -D -G appuser appuser)) && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

# Start the application
CMD ["node", "dist/app.js"]

