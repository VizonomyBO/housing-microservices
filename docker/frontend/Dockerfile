# Frontend Dockerfile - Builds React Router app from GitHub
ARG GITHUB_TOKEN
ARG VITE_PUBLIC_CONTENT_URL
FROM node:20-alpine AS builder

# Install git for cloning
RUN apk add --no-cache git

# Clone the frontend repository and checkout start-conversation branch
ARG GITHUB_TOKEN
# Use CACHEBUST to force fresh clone: docker build --build-arg CACHEBUST=$(date +%s) ...
ARG CACHEBUST=1
WORKDIR /app
# Clone using GITHUB_TOKEN for authentication
RUN echo "Cache bust: $CACHEBUST" && \
    echo "DEBUG: GITHUB_TOKEN length = ${#GITHUB_TOKEN}" && \
    if [ -z "$GITHUB_TOKEN" ]; then \
      echo "ERROR: GITHUB_TOKEN build arg is empty or not set"; \
      echo "Check: docker-compose build args and .env file"; \
      exit 1; \
    fi && \
    git clone --depth 1 --branch start-conversation \
      https://${GITHUB_TOKEN}@github.com/VizonomyBO/housing-frontend.git frontend

WORKDIR /app/frontend
# Ensure we have the absolute latest commits
RUN git fetch origin start-conversation && git reset --hard origin/start-conversation

# Set Vite environment variable for build
ARG VITE_PUBLIC_CONTENT_URL
ENV VITE_PUBLIC_CONTENT_URL=${VITE_PUBLIC_CONTENT_URL}

# Install dependencies and build
RUN npm ci && npm run build

# Production stage
FROM node:20-alpine

# Install curl for healthchecks
RUN apk add --no-cache curl

WORKDIR /app

# Copy built application from builder
COPY --from=builder /app/frontend .

# Expose port
EXPOSE 3000

# Start the application
# React Router typically uses npm start or npm run start:prod
CMD ["sh", "-c", "npm run start:prod || npm start || node server.js || node index.js"]

