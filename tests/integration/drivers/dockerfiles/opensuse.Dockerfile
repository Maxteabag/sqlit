FROM opensuse/leap:15

RUN zypper refresh && zypper install -y \
    python311 \
    python311-pip \
    python311-devel \
    curl \
    unixODBC-devel \
    gcc \
    && zypper clean -a

RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && pip install pyodbc

WORKDIR /app
COPY sqlit/ /app/sqlit/
COPY pyproject.toml README.md /app/

RUN pip install -e .

COPY tests/integration/drivers/test_driver_install.py /app/test_driver_install.py

CMD ["python3", "/app/test_driver_install.py"]
