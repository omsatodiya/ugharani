FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY ugharani ./ugharani
RUN uv sync --frozen --no-dev

# Free hosting wipes the disk on restart: start from sample buyers, keep data in /tmp.
ENV DEMO_SEED=1 LEDGER_DB=/tmp/ugharani.db AUDIO_CACHE=/tmp/tts
CMD ["sh", "-c", "uv run --no-sync uvicorn ugharani.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
