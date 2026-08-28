# Shared image for the api, worker and sim services. They run the same codebase
# and differ only by entrypoint (ARCHITECTURE.md Section 3): a 200-replication
# Monte Carlo run must never block an HTTP request.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY connector/__init__.py ./connector/
COPY evaluation/__init__.py ./evaluation/
COPY plantsim/__init__.py ./plantsim/
COPY tools/__init__.py ./tools/
COPY twin/__init__.py ./twin/
RUN python -m pip install --upgrade pip && python -m pip install -e .

COPY . .

CMD ["python", "-c", "print('Set a command in docker-compose.yml')"]
