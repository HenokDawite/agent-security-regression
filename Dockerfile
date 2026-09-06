FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MCP_FILESYSTEM_BIN=/usr/local/bin/mcp-server-filesystem \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g @modelcontextprotocol/server-filesystem \
    && test -x /usr/local/bin/mcp-server-filesystem \
    && npm cache clean --force \
    && apt-get purge -y npm \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /root/.npm

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_security /app/agent_security
COPY scripts /app/scripts
COPY sandbox /app/sandbox

RUN gid=1000 \
    && getent group "$gid" >/dev/null || groupadd --gid "$gid" app \
    && useradd --uid 1000 --gid "$gid" --create-home --home-dir /home/app app \
    && chmod -R a+rX /app

USER app
