# Build: docker build -t floodroute-api:dev -f apps/api/Dockerfile apps/api
# API:    docker compose up api
# Worker: docker compose up worker
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

# Mirror repo depth so score/config.py parents[4] resolves to /app at runtime.
WORKDIR /app/apps/api
COPY pyproject.toml ./
COPY floodroute/ ./floodroute/
RUN uv pip install --system --no-cache .

RUN useradd --system --create-home --shell /bin/false floodroute \
    && chown -R floodroute:floodroute /app
USER floodroute

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080
CMD ["uvicorn", "floodroute.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
