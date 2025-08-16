"""Shared test utilities for fileindex tests."""


def process_media_queue_synchronously():
    """Helper to process media analysis queue jobs synchronously in tests.
    
    This is now a no-op since task processing has been moved to the application layer.
    Apps using django-fileindex should implement their own task processing.
    """
    pass