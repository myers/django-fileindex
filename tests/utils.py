"""Shared test utilities for fileindex tests."""

from pgq.models import Job

from fileindex.queues import media_analysis_queue


def process_media_queue_synchronously():
    """Helper to process media analysis queue jobs synchronously in tests."""
    # Process all pending jobs in the media analysis queue
    # Jobs don't have state - they're either in the queue or not
    jobs = Job.objects.filter(queue=media_analysis_queue.queue)
    for job in jobs:
        # Get the actual task function from the queue's tasks dict
        # The task function expects (queue, job) - the @retry decorator handles the rest
        task_func = media_analysis_queue.tasks.get(job.task)
        if task_func:
            task_func(media_analysis_queue, job)

        # Delete the job after processing (like dequeue does)
        job.delete()
