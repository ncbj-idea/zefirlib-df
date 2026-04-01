#!/bin/sh
set -e

CURRENT=$(alembic current)
HEAD=$(alembic heads)

if [ "$CURRENT" != "$HEAD" ] && [ -n "$HEAD" ]; then
    echo "Running migrations ($CURRENT -> $HEAD)..."
    python -m alembic upgrade head
else
    echo "Database migrations up to date"
fi

exec "$@"
