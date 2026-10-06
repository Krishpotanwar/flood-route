# Build from the repository root so the API serves the citizen frontend at /app/.
FROM node:24-bookworm-slim AS citizen
WORKDIR /src
RUN npm install --global pnpm@10.28.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/ui/ ./packages/ui/
COPY apps/citizen/package.json ./apps/citizen/package.json
RUN pnpm install --frozen-lockfile
COPY apps/citizen/ ./apps/citizen/
RUN pnpm --filter @floodroute/citizen build

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

# Mirror repo depth so score/config.py parents[4] resolves to /app at runtime.
WORKDIR /app/apps/api
COPY apps/api/pyproject.toml ./
COPY apps/api/floodroute/ ./floodroute/
RUN UV_HTTP_TIMEOUT=30 UV_HTTP_RETRIES=1 uv pip install --system --no-cache .
COPY --from=citizen /src/apps/citizen/dist/ /app/apps/citizen/dist/
COPY data/config/ /app/data/config/
COPY data/inventory/ /app/data/inventory/

RUN useradd --system --create-home --shell /bin/false floodroute \
    && mkdir -p /app/data/snapshots /app/apps/data/photos \
    && chown -R floodroute:floodroute /app
USER floodroute

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080
CMD ["uvicorn", "floodroute.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
