#!/usr/bin/env bash
# Optional isolation for live Anthropic + MCP runs.
# One disposable container per invocation (including an entire replay batch).
# Does not fall back to host execution if Docker is unavailable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${ASL_IMAGE:-agent-security-lab:latest}"

usage() {
  echo "Usage: scripts/run_in_docker.sh scripts/run_scenario.py scenarioN" >&2
  echo "       scripts/run_in_docker.sh scripts/replay_scenario.py scenarioN N" >&2
  echo "Docker isolates host filesystem/process boundaries, not outbound network destinations." >&2
  exit 2
}

if [[ $# -lt 1 ]]; then
  usage
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "error: Docker is not installed or not on PATH." >&2
  echo "Install Docker and retry. This wrapper does not fall back to host execution." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker is installed but the daemon is not available." >&2
  echo "Start Docker and retry. This wrapper does not fall back to host execution." >&2
  exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "error: image $IMAGE not found. Build it with:" >&2
  echo "  docker build -t $IMAGE \"$ROOT\"" >&2
  exit 1
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" && -f "$ROOT/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    if [[ "$line" == ANTHROPIC_API_KEY=* ]]; then
      ANTHROPIC_API_KEY="${line#ANTHROPIC_API_KEY=}"
      ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY#\"}"
      ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY%\"}"
      ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY#\'}"
      ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY%\'}"
    fi
  done < "$ROOT/.env"
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "error: ANTHROPIC_API_KEY is not set and was not found in .env." >&2
  exit 1
fi

mkdir -p "$ROOT/logs" "$ROOT/sandbox"
export ANTHROPIC_API_KEY

# Host uid/gid so bind-mounted sandbox/ and logs/ are writable on Linux
# without chowning those directories to the image's default user.
docker run --rm \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m \
  --pids-limit 256 \
  --memory 1g \
  --user "$(id -u):$(id -g)" \
  --env ANTHROPIC_API_KEY \
  --env HOME=/tmp \
  --env MCP_FILESYSTEM_BIN=/usr/local/bin/mcp-server-filesystem \
  --mount "type=bind,src=${ROOT}/sandbox,dst=/app/sandbox" \
  --mount "type=bind,src=${ROOT}/logs,dst=/app/logs" \
  --workdir /app \
  "$IMAGE" \
  python "$@"
