"""
Django FileIndex - A Django app for file deduplication and indexing using SHA hashes.
"""

# Latest migration name for external apps to depend on
# This allows other Django apps to safely reference our migrations
# without hardcoding migration names
LATEST_MIGRATION = "0002_alter_indexedfile_size_to_biginteger"

# For backward compatibility, also provide the initial migration
INITIAL_MIGRATION = "0001_initial"

__version__ = "0.4.1"