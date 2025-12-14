FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY github_release_watcher ./github_release_watcher

RUN pip install --no-cache-dir .

EXPOSE 8000

VOLUME ["/data"]

ENTRYPOINT ["github-release-watcher"]

CMD ["--config", "/data/config.toml", "--web", "--web-host", "0.0.0.0", "--web-port", "8000"]
