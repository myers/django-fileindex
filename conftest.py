import os
import subprocess
import time
import pytest
from django.conf import settings


def pytest_configure(config):
    """Configure pytest and start docker-compose if needed."""
    # Check if we should use PostgreSQL for tests
    use_postgres = os.environ.get('USE_POSTGRES', 'true').lower() == 'true'
    
    if use_postgres:
        # Start docker-compose
        print("Starting PostgreSQL with docker-compose...")
        subprocess.run(['docker-compose', 'up', '-d'], check=True)
        
        # Wait for PostgreSQL to be ready
        max_attempts = 30
        for i in range(max_attempts):
            result = subprocess.run(
                ['docker-compose', 'exec', '-T', 'postgres', 'pg_isready', '-U', 'fileindex'],
                capture_output=True
            )
            if result.returncode == 0:
                print("PostgreSQL is ready!")
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL failed to start within 30 seconds")


def pytest_unconfigure(config):
    """Stop docker-compose after tests."""
    use_postgres = os.environ.get('USE_POSTGRES', 'true').lower() == 'true'
    
    if use_postgres:
        print("Stopping PostgreSQL...")
        subprocess.run(['docker-compose', 'down'], check=True)


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """Override the default django_db_setup to ensure proper test database setup."""
    with django_db_blocker.unblock():
        # The test database is already created by Django
        pass