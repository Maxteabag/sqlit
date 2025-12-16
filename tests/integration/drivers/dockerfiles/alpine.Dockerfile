FROM alpine:3.20

# Install Python and basic tools
RUN apk add --no-cache \
    python3 \
    py3-pip \
    curl \
    bash \
    unixodbc \
    unixodbc-dev \
    g++ \
    python3-dev

# Create virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install pyodbc

# Copy the sqlit package
WORKDIR /app
COPY sqlit/ /app/sqlit/
COPY pyproject.toml README.md /app/

# Install sqlit in development mode
RUN pip install -e .

# Copy test script
COPY tests/integration/drivers/test_driver_install.py /app/test_driver_install.py

CMD ["python3", "/app/test_driver_install.py"]
