#!/bin/bash
# EC2 user-data for the Launch Template (Amazon Linux 2023).
# Every new instance created by the Auto Scaling Group runs this on first boot,
# so it builds and starts the app with zero manual work.
set -euxo pipefail

REPO_URL="https://github.com/<your-username>/<your-repo>.git"   # <-- CHANGE THIS (repo must be public)

dnf install -y docker git
systemctl enable --now docker

git clone "$REPO_URL" /opt/tatkal
cd /opt/tatkal/app
docker build -t tatkal .

# Host port 80 -> container port 3000; restart automatically if it crashes/reboots
docker run -d --name tatkal --restart always \
  -p 80:3000 \
  -e HOST_NAME="$(hostname)" \
  tatkal
