# Job Service

Scheduled job service for housing microservices. Handles automated tasks like report pre-generation.

## Features

- **Report Pre-Generation**: Automatically generates housing reports for all countries on the 25th of each month, caching them for the next month.
- **REST API**: Health checks, job status, and manual triggering
- **APScheduler**: Reliable cron-like scheduling

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `JOB_SERVICE_PORT` | 8090 | HTTP port |
| `LOG_LEVEL` | INFO | Logging level |
| `JOB_SCHEDULE_DAY` | 25 | Day of month to run pre-generation (1-28) |
| `JOB_SCHEDULE_HOUR` | 2 | Hour to run (0-23) |
| `JOB_SCHEDULE_MINUTE` | 0 | Minute to run (0-59) |
| `JOB_RUN_ON_STARTUP` | false | Run job immediately on startup |
| `AGENT_BASE_URL` | http://agent-api:8000 | Agent API URL |
| `AUTH_BASE_URL` | http://auth-service:5000 | Auth service URL |
| `JOB_SERVICE_EMAIL` | - | Service account email |
| `JOB_SERVICE_PASSWORD` | - | Service account password |
| `JOB_REPORT_ACCESS_SCOPE` | base | Filter documents by access scope |
| `JOB_REPORT_TIMEOUT_SECONDS` | 600 | Timeout per report generation |
| `JOB_DELAY_BETWEEN_REPORTS` | 5 | Seconds between report generations |

## API Endpoints

### Health Check
```
GET /health
```

### Scheduler Status
```
GET /v1/scheduler/status
```
Returns information about scheduled jobs and next run times.

### Job Status
```
GET /v1/jobs/report-pregeneration/status
```
Returns whether the job is running and the last result.

### Trigger Job Manually
```
POST /v1/jobs/report-pregeneration/trigger?target_month=2026-02
```
Manually trigger report pre-generation. If `target_month` is not specified, uses next month.

### Last Result
```
GET /v1/jobs/report-pregeneration/last-result
```
Returns details of the last job execution.

## Local Development

```bash
cd services/job-service

# Create venv and install
uv venv --python 3.13 .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv sync

# Set environment variables
export JOB_SERVICE_EMAIL="your-email@example.com"
export JOB_SERVICE_PASSWORD="your-password"
export AGENT_BASE_URL="http://localhost:8000"
export AUTH_BASE_URL="http://localhost:5001"

# Run with reload
python run.py
```

## Docker

The service is included in both `docker-compose.yml` (local) and `docker-compose.ec2.yml` (production).

```bash
# Start with other services
docker compose up -d job-service

# View logs
docker compose logs -f job-service

# Manually trigger job
curl -X POST http://localhost:8090/v1/jobs/report-pregeneration/trigger
```

## Schedule

By default, the job runs on the **25th of each month at 2:00 AM**. This gives 5-6 days before month-end to pre-generate all reports for the next month.

The schedule can be customized via environment variables:
- `JOB_SCHEDULE_DAY`: Day of month (1-28)
- `JOB_SCHEDULE_HOUR`: Hour (0-23)
- `JOB_SCHEDULE_MINUTE`: Minute (0-59)

## Testing

```bash
# Trigger immediate run on startup
JOB_RUN_ON_STARTUP=true docker compose up job-service

# Manual trigger via API
curl -X POST "http://localhost:8090/v1/jobs/report-pregeneration/trigger?target_month=2026-02"

# Check status
curl http://localhost:8090/v1/jobs/report-pregeneration/status
```

