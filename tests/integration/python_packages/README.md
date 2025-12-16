# Python Driver Install Flow Tests

Validates the end-user flow for missing Python DB drivers:

1. User attempts to save a new connection
2. App prompts to install the missing driver
3. App shows a loading screen while installing
4. App shows success message, or failure with manual install instructions

## Run

```bash
./run_tests.sh
```

## Screenshots

This integration test can export Textual screenshots (SVG) from inside the container to the host:

- Output directory: `tests/integration/python_packages/artifacts/`
- Enable via `SQLIT_TEST_SCREENSHOTS_DIR=/artifacts` (already set in `tests/integration/python_packages/docker-compose.yml`)

## Requirements

- Docker + Docker Compose
- Network access (to download driver wheels)
