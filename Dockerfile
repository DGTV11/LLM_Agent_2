FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ADD . /app

WORKDIR /app

RUN uv sync --locked --compile-bytecode

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
