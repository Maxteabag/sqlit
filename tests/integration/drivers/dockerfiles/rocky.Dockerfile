FROM rockylinux:9

RUN dnf install -y epel-release && \
    dnf config-manager --set-enabled crb && \
    dnf install -y \
    python3.11 \
    python3.11-pip \
    python3.11-devel \
    unixODBC-devel \
    gcc \
    && dnf clean all

RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && pip install pyodbc

WORKDIR /app
COPY sqlit/ /app/sqlit/
COPY pyproject.toml README.md /app/

RUN pip install -e .

COPY tests/integration/drivers/test_driver_install.py /app/test_driver_install.py

CMD ["python3", "/app/test_driver_install.py"]
