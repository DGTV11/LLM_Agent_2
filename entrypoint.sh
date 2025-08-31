#!/bin/sh
set -e

exec uv run fastapi run main.py --host 0.0.0.0 --port 5047
# exec uv run fastapi dev main.py --host 0.0.0.0 --port 5046
