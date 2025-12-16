#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

docker compose up --build --abort-on-container-exit --exit-code-from test-debian test-debian
