FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends x11vnc novnc websockify openbox openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/snapchat-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/snapchat-requirements.txt \
    && python -m playwright install chrome \
    && (id pwuser >/dev/null 2>&1 && userdel -r pwuser || true) \
    && useradd --uid 1000 --create-home --home-dir /home/container --shell /bin/bash container

COPY --chown=container:container . /opt/snapchat-automator
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

USER container
ENV USER=container HOME=/home/container PYTHONUNBUFFERED=1
WORKDIR /home/container
CMD ["/bin/bash", "/entrypoint.sh"]
