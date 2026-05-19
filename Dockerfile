FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

RUN pip install --no-cache-dir -e .

RUN mkdir -p /spool/downloads /spool/prepared /spool/fallback /spool/tmp /spool/reports

EXPOSE 8000

CMD ["app", "api"]
