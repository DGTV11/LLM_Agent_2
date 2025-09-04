FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y docker.io libmagic1

ADD . /app

WORKDIR /app

RUN uv sync --locked --compile-bytecode

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
