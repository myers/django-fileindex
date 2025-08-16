from pgq.queue import AtLeastOnceQueue

# Use the existing media_analysis queue name to avoid migration
media_processing_queue = AtLeastOnceQueue(
    tasks={},
    queue="media_analysis",  # Keep existing queue name
    notify_channel="media_analysis",
)

# Backwards compatibility aliases
avif_creation_queue = media_processing_queue
media_analysis_queue = media_processing_queue
