# Shared image for the api, worker and sim services. They run the same codebase
# and differ only by entrypoint (ARCHITECTURE.md Section 3): a 200-replication
# Monte Carlo run must never block an HTTP request.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp is the only system library needed at runtime: LightGBM links against
# it. There is no compiler here, because every dependency in pyproject.toml
# ships a manylinux wheel for CPython 3.11 and a toolchain would add several
# hundred megabytes to a cold start that has a five minute budget (NFR-05).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
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
