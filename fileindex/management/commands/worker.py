import logging

from pgq.commands import Worker

from fileindex.queues import media_processing_queue

logger = logging.getLogger(f"goodstuff.{__name__}")

logger.info("Starting worker")


class Command(Worker):
    queue = media_processing_queue
    logger = logger
