#!/bin/bash
# Script to run tests with PostgreSQL

# Start PostgreSQL
echo "Starting PostgreSQL with docker-compose..."
docker-compose up -d

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker-compose exec -T postgres pg_isready -U fileindex >/dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo -n "."
    sleep 1
done

# Run tests with PostgreSQL settings
echo "Running tests with PostgreSQL..."
DJANGO_SETTINGS_MODULE=tests.settings_postgres uv run pytest --cov=fileindex --cov-report=html -v

# Stop PostgreSQL
echo "Stopping PostgreSQL..."
docker-compose down

echo "Done!"