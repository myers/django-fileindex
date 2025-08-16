import logging

logger = logging.getLogger(__name__)


def enqueue_video_thumbnail(indexed_file):
    """Enqueue video thumbnail generation for a video IndexedFile."""
    # Skip if not a video
    if not indexed_file.mime_type or not indexed_file.mime_type.startswith("video/"):
        logger.info(f"Skipping {indexed_file.path} - not a video file")
        return

    # Skip if thumbnail already exists
    if indexed_file.derived_files.filter(derived_for="thumbnail").exists():
        logger.info(f"Skipping {indexed_file.path} - thumbnail already exists")
        return

    # Import here to avoid circular import
    from fileindex.tasks import generate_video_thumbnail

    generate_video_thumbnail.enqueue({"indexed_file_id": indexed_file.id})
