FROM python:3.12-slim

WORKDIR /app

COPY . /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends librsvg2-bin \
  && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip \
  && pip install -e ".[test]"

CMD ["python", "tests/integration/drivers/test_driver_setup_ui_flow.py"]
