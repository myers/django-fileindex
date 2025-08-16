import logging

from pgq.commands import Worker

from fileindex.queues import avif_creation_queue

logger = logging.getLogger(f"goodstuff.{__name__}")

logger.info("Starting worker")


class Command(Worker):
    queue = avif_creation_queue
    logger = logger
