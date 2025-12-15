# Tasks

## Patch Deploys on EC2 (Python Services)
**Last performed:** [date]
**Files to modify:**
- `services/agent-api/src/...` (or other service files)

**Steps:**
1.  **Prep env/SSH**:
    -   `env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a`
    -   Check health: `ssh -i ArchaaS/dist/vizonomy-v2-ec2-dev2.pem ec2-user@${POSTGRES_HOST} "echo ok && uptime"`

2.  **Copy patched file to EC2**:
    -   `scp -i ArchaaS/dist/vizonomy-v2-ec2-dev2.pem path/to/local_file.py ec2-user@${POSTGRES_HOST}:/tmp/local_file.py`

3.  **Copy into container**:
    -   Find container: `sudo docker ps --format '{{.Names}}' | grep agent-api`
    -   Copy: `sudo docker cp /tmp/local_file.py <container>:/app/services/agent-api/src/.../file.py`

4.  **Restart service**:
    -   `sudo docker compose -f /opt/housing-microservices/docker-compose.ec2.yml restart agent-api`
    -   Check health: `sudo docker ps --format '{{.Names}} {{.Status}}' | grep agent-api`

5.  **Verify**:
    -   Health: `curl http://localhost:8000/health` on EC2.
    -   Targeted check: Run a `/v1/chat` request or `scripts/prod_smoke_check.sh` in AWS mode.

**Important notes:**
-   Avoid full redeploys for small patches.
-   If multiple files change, repeat the `docker cp` step per file before a single restart.
-   Use `.env.prod` for AWS targets.

## End-to-End Ingestion Smoke Suite
**Last performed:** [date]
**Files to modify:**
- `packages/shared_data_layer/tests/test_end_to_end_ingestion.py`

**Steps:**
1.  Run the suite explicitly with the `--end-to-end` flag:
    ```bash
    .venv/bin/pytest --end-to-end tests/test_end_to_end_ingestion.py -n 0
    ```

**Important notes:**
-   These tests are **opt-in** and default to `skip`.
-   They stitch together document ingestion, chunk activation, and knowledge-graph rollups.
