# Frontend Dockerfile - Builds React Router app from GitHub
ARG GITHUB_TOKEN
ARG VITE_PUBLIC_CONTENT_URL
FROM node:20-alpine AS builder

# Install git for cloning
RUN apk add --no-cache git

# Clone the frontend repository and checkout start-conversation branch
ARG GITHUB_TOKEN
WORKDIR /app
RUN if [ -n "$GITHUB_TOKEN" ]; then \
      git clone https://${GITHUB_TOKEN}@github.com/VizonomyBO/housing-frontend.git frontend; \
    else \
      echo "Warning: GITHUB_TOKEN not provided, attempting public clone"; \
      git clone https://github.com/VizonomyBO/housing-frontend.git frontend || exit 1; \
    fi

WORKDIR /app/frontend
RUN git checkout start-conversation || echo "Warning: start-conversation branch not found, using default branch"

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

