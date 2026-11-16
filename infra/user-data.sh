#!/bin/bash
# EC2 user-data for the Launch Template (Amazon Linux 2023).
# Every new instance created by the Auto Scaling Group runs this on first boot,
# so it builds and starts the app with zero manual work.
set -euxo pipefail

REPO_URL="https://github.com/202611051-Fenil/irctc-tatkal-autoscaling.git"   # public repo

dnf install -y docker git
systemctl enable --now docker

git clone "$REPO_URL" /opt/tatkal
cd /opt/tatkal/app
docker build -t tatkal .

# Ask the EC2 metadata service which zone and instance this is (shown on the dashboard).
# "|| echo unknown" keeps boot going even if the lookup fails.
TOKEN=$(curl -s --max-time 3 -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || echo "")
AZ=$(curl -s --max-time 3 -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/availability-zone || echo unknown)
INSTANCE_ID=$(curl -s --max-time 3 -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id || echo unknown)

# Host port 80 -> container port 3000; restart automatically if it crashes/reboots
docker run -d --name tatkal --restart always \
  -p 80:3000 \
  -e HOST_NAME="$(hostname)" \
  -e AZ="$AZ" \
  -e INSTANCE_ID="$INSTANCE_ID" \
  tatkal
