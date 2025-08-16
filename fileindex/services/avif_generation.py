import logging

logger = logging.getLogger(__name__)


def enqueue_creating_avif_from_gif(indexed_file):
    """Enqueue AVIF creation from GIF using IndexedFile with JSON metadata."""
    # Get dimensions from metadata JSON field
    width = indexed_file.metadata.get("width")
    height = indexed_file.metadata.get("height")

    # Skip if dimensions are missing or too small
    if not width or not height or width < 64 or height < 64:
        logger.info(
            f"Skipping {indexed_file.path} - width or height missing or smaller than 64 px"
        )
        return

    # Skip GIFs longer than 30 seconds and smaller than 1MB
    duration_ms = indexed_file.metadata.get("duration", 0)
    duration_sec = duration_ms / 1000.0 if duration_ms else 0
    if duration_sec > 30 and indexed_file.size < 1024 * 1024:
        logger.info(f"Skipping {indexed_file.path} - long duration but small size")
        return

    # Import here to avoid circular import
    from fileindex.tasks import create_avif_from_gif

    create_avif_from_gif.enqueue({"indexed_file_id": indexed_file.id})
