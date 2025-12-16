FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    gnupg \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && pip install pyodbc

WORKDIR /app
COPY sqlit/ /app/sqlit/
COPY pyproject.toml README.md /app/

RUN pip install -e .

COPY tests/integration/drivers/test_driver_install.py /app/test_driver_install.py

CMD ["python3", "/app/test_driver_install.py"]
