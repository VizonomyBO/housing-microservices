#!/bin/bash
set -euo pipefail

# Minimal EC2 bootstrap for cache-free stack (agent, ingestion, auth, user, Postgres on host).
# Installs Docker + Compose plugin and prepares the deploy workspace; service rollout is handled
# by the deployment automation script (see scripts/deploy_stack.sh).

export HOME=/root
LOG_FILE=/var/log/housing-bootstrap.log

exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== Bootstrapping housing stack prerequisites at $(date) ==="

dnf update -y
dnf install -y docker git python3 tar curl

mkdir -p /usr/local/lib/docker/cli-plugins
curl -sSL "https://github.com/docker/compose/releases/download/v2.31.0/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose

systemctl enable --now docker
usermod -aG docker ec2-user || true

mkdir -p /opt/housing-microservices
chown -R ec2-user:ec2-user /opt/housing-microservices

echo "Bootstrap complete. Run the deployment script from the repo to roll out services." >> "$LOG_FILE"
