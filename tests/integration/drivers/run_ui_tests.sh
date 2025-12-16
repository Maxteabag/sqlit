#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

docker compose -f docker-compose.ui.yml up --build --abort-on-container-exit --exit-code-from ui-test ui-test
