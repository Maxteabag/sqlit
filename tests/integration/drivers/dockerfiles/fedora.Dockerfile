FROM fedora:40

RUN dnf install -y \
    python3 \
    python3-pip \
    curl \
    unixODBC-devel \
    gcc \
    python3-devel \
    && dnf clean all

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && pip install pyodbc

WORKDIR /app
COPY sqlit/ /app/sqlit/
COPY pyproject.toml README.md /app/

RUN pip install -e .

COPY tests/integration/drivers/test_driver_install.py /app/test_driver_install.py

CMD ["python3", "/app/test_driver_install.py"]
