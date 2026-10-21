FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements-lock.txt ./
RUN python -m pip install --require-hashes -r requirements-lock.txt \
    && groupadd --gid 10001 petshop \
    && useradd --uid 10001 --gid petshop --no-create-home petshop \
    && install -d -o petshop -g petshop -m 0755 /app/uploads/reviews

COPY --chown=petshop:petshop app ./app
COPY --chown=petshop:petshop migrations ./migrations
COPY --chown=petshop:petshop alembic.ini ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=10s --start-period=120s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=5).close()"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
