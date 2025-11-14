# User Service Quick Start Guide

## Overview

The User Service is a Flask-based microservice for managing user profiles and information. It shares the same database as the auth-service and provides endpoints for user management.

## Quick Start

### 1. Local Development

```bash
# Navigate to user-service directory
cd services/user-service

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run the service
python run.py
```

The service will be available at `http://localhost:5001`

### 2. Docker Compose

From the project root:

```bash
# Start all services including user-service
docker-compose up -d

# View logs
docker-compose logs -f user-service

# Stop services
docker-compose down
```

The service will be available at `http://localhost:5002`

## Testing the API

### Get Current User Profile

```bash
# First, get a token from auth-service
TOKEN=$(curl -X POST http://localhost:5001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r '.access_token')

# Get your profile
curl http://localhost:5002/users/me \
  -H "Authorization: Bearer $TOKEN"
```

### Update Current User Profile

```bash
curl -X PUT http://localhost:5002/users/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Jane",
    "last_name": "Doe",
    "country_code": "CAN"
  }'
```

### List All Users (Admin Only)

```bash
# Get admin token
ADMIN_TOKEN=$(curl -X POST http://localhost:5001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}' \
  | jq -r '.access_token')

# List users
curl http://localhost:5002/users?page=1&per_page=20 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Get User by ID (Admin or Self)

```bash
curl http://localhost:5002/users/123 \
  -H "Authorization: Bearer $TOKEN"
```

### Search Users (Admin Only)

```bash
curl "http://localhost:5002/users/search?q=john&limit=10" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Update User (Admin Only)

```bash
curl -X PUT http://localhost:5002/users/123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Updated",
    "role": "staff",
    "status": "active"
  }'
```

### Delete User (Admin Only)

```bash
curl -X DELETE http://localhost:5002/users/123 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## API Endpoints Summary

### Public Endpoints
- `GET /` - Service info
- `GET /health` - Health check

### Authenticated Endpoints
- `GET /users/me` - Get current user
- `PUT /users/me` - Update current user
- `GET /users/<id>` - Get user by ID (self or admin)

### Admin Only Endpoints
- `GET /users` - List all users (paginated)
- `GET /users/search` - Search users
- `PUT /users/<id>` - Update any user
- `DELETE /users/<id>` - Delete user

## Running Tests

```bash
# Install test dependencies
pip install -r requirements/test.txt

# Run all tests
make test

# Run with coverage
make coverage

# Run only unit tests
make test-unit

# Run only integration tests
make test-integration
```

## Development Commands

```bash
# Format code
make format

# Run linters
make lint

# Clean temporary files
make clean
```

## Environment Variables

Key environment variables:

- `PORT` - Service port (default: 5001)
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - Must match auth-service key
- `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` - Token expiration (default: 15)
- `DEBUG` - Enable debug mode (default: False)

## Architecture Integration

The user-service integrates with:

1. **Auth Service**: Uses the same JWT secret for token validation
2. **PostgreSQL**: Shares the same database for user data
3. **Swagger Service**: Documentation aggregated automatically

## Security Notes

1. All endpoints (except `/` and `/health`) require authentication
2. JWT tokens must be issued by the auth-service
3. Regular users can only access their own profile
4. Admin users can access and modify all profiles
5. Users cannot delete themselves (even admins)

## Troubleshooting

### Service won't start

Check:
- Database connection (DATABASE_URL)
- Port availability (default: 5001)
- JWT_SECRET_KEY matches auth-service

### Authentication fails

Verify:
- JWT_SECRET_KEY matches auth-service
- Token is valid and not expired
- Authorization header format: `Bearer <token>`

### Database errors

Ensure:
- PostgreSQL is running
- Database exists
- User has proper permissions
- Connection string is correct

## Next Steps

1. Implement additional user-related features
2. Add user preferences/settings endpoints
3. Add user avatar upload
4. Implement user activity logging
5. Add email notification integration

