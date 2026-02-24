from invoke import task


@task
def makemigrations(c):
    """Generate Django migrations for the fileindex app."""
    c.run(
        'uv run python -c "'
        "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings'); "
        "from django.core.management import execute_from_command_line; "
        "execute_from_command_line(['manage.py', 'makemigrations', 'fileindex'])"
        '"'
    )
