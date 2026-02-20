FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
LABEL maintainer="Narendranath" description="JobScout — Self-recovering job pipeline"

RUN groupadd -r scout && useradd -r -g scout -m scout
COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=scout:scout . .
RUN mkdir -p /home/scout/.job_scout && chown -R scout:scout /home/scout/.job_scout

USER scout

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${HEALTH_PORT:-8089}/health')" || exit 1

EXPOSE ${HEALTH_PORT:-8089}
ENTRYPOINT ["python", "main.py"]
