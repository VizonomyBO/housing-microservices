# Quick Start Guide

Get the microservices platform up and running in 5 minutes!

## Prerequisites

- Docker Desktop installed and running
- Git installed

## Step 1: Clone and Setup (1 minute)

```bash
# Clone the repository
git clone <your-repo-url>
cd ia-project

# Copy environment file
cp env.example .env
```

## Step 2: Start Services (2 minutes)

```bash
# Build and start all services
docker-compose up --build -d

# Wait for services to be healthy (about 30-60 seconds)
docker-compose ps
```

You should see all services with "healthy" status.

## Step 3: Verify Everything Works (1 minute)

### Check Service Health

```bash
# Check all services
curl http://localhost:3000/api/status
```

### Open API Documentation

Open in your browser:
- **API Docs**: http://localhost:3000/docs
- **Landing Page**: http://localhost:3000

## Step 4: Test the API (1 minute)

### Register a User

```bash
curl -X POST http://localhost:5000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "username": "demouser",
    "password": "DemoPass123!",
    "first_name": "Demo",
    "last_name": "User"
  }'
```

### Login

```bash
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "login": "demo@example.com",
    "password": "DemoPass123!"
  }'
```

## 🎉 You're Done!

### What's Running?

- **Swagger Aggregator**: http://localhost:3000 - Unified API documentation
- **Account Service**: http://localhost:5000 - Authentication API
- **PostgreSQL**: localhost:5432 - Database

### Next Steps

- Explore the interactive API docs at http://localhost:3000/docs
- Check system status at http://localhost:3000/api/status
- View detailed metrics at http://localhost:3000/health/metrics
- Read the full README.md for advanced features

### Useful Commands

```bash
# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Restart services
docker-compose restart

# Clean everything (including database)
docker-compose down -v
```

### Using Make (Optional)

If you have `make` installed:

```bash
make help          # Show all available commands
make up            # Start services
make logs          # View logs
make health        # Check health
make status        # Show system status
make test-register # Test registration
make test-login    # Test login
make open-docs     # Open docs in browser
```

## Troubleshooting

### Port Already in Use

If you get port conflicts:

```bash
# Check what's using the ports
lsof -i :3000
lsof -i :5000
lsof -i :5432

# Kill the process or change ports in docker-compose.yml
```

### Services Not Healthy

```bash
# Check logs for errors
docker-compose logs

# Restart services
docker-compose restart

# Rebuild from scratch
docker-compose down -v
docker-compose up --build
```

### Database Connection Failed

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# View database logs
docker-compose logs postgres

# Access database directly
docker-compose exec postgres psql -U account_user -d account_db
```

## Need Help?

- Check the full [README.md](README.md) for detailed documentation
- Review logs: `docker-compose logs`
- Check service status: `curl http://localhost:3000/api/status`

---

Happy coding! 🚀

