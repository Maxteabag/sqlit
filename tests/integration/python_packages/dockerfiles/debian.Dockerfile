FROM python:3.12-slim

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip \
  && pip install -e ".[test]"

ENV SQLIT_CONFIG_DIR=/tmp/sqlit-config
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "/app/tests/integration/python_packages/test_package_install_flow.py"]
