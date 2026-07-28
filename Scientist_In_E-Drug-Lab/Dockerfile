FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxrender1 libxext6 libsm6 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY config ./config
COPY tests ./tests
COPY schemas ./schemas
COPY skills ./skills
COPY examples ./examples

RUN pip install --no-cache-dir -e ".[dev]"

ENV MASLD_COMPETITION_EVAL_MODE=true
ENV PYTHONUNBUFFERED=1

CMD ["masld-agent", "offline-demo", "--fixture", "tests/fixtures/hsd17b13", "--output", "runs"]
