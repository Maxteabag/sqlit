FROM archlinux:latest

RUN pacman -Syu --noconfirm && pacman -S --noconfirm \
    python \
    python-pip \
    python-virtualenv \
    curl \
    base-devel \
    git \
    unixodbc

RUN useradd -m builder && echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

USER builder
WORKDIR /home/builder
RUN git clone https://aur.archlinux.org/yay.git && cd yay && makepkg -si --noconfirm && cd .. && rm -rf yay

USER root
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && pip install pyodbc

WORKDIR /app
COPY sqlit/ /app/sqlit/
COPY pyproject.toml README.md /app/
RUN pip install -e .

COPY tests/integration/drivers/test_driver_install.py /app/test_driver_install.py

USER builder
CMD ["sudo", "-E", "/opt/venv/bin/python", "/app/test_driver_install.py"]
