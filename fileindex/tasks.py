import contextlib
import logging
import select
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from pgq.decorators import JobMeta, task
from pgq.models import Job
from pgq.queue import Queue

from fileindex.models import IndexedFile
from fileindex.queues import avif_creation_queue, media_analysis_queue


class SubprocessError(RuntimeError):
    pass


def run_subprocess(command):
    """
    Run a subprocess and show stdout and stderr in real time.

    :param command: List of command arguments to execute.
    """
    print(command)
    # Start the process
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Create a list to keep track of the outputs for real-time processing
    outputs = [process.stdout, process.stderr]

    try:
        # Monitor both stdout and stderr for output
        while True:
            # Wait for data to become available on either stdout or stderr
            readable, _, _ = select.select(outputs, [], [])

            for stream in readable:
                line = stream.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    if stream is process.stdout:
                        print("STDOUT:", line)
                    else:
                        print("STDERR:", line)
                else:
                    # Remove the stream from the list if it is exhausted
                    outputs.remove(stream)
                    stream.close()

            # Break out of the loop if both streams are exhausted
            if not outputs:
                break

    except KeyboardInterrupt:
        print("Process interrupted by user")
    finally:
        # Clean up
        process.stdout.close()
        process.stderr.close()
        process.terminate()
        exit_status = process.wait()
        if exit_status != 0:
            raise SubprocessError(f"command failed with exit code {exit_status}")


logger = logging.getLogger(f"goodstuff.{__name__}")


@task(avif_creation_queue)
def create_avif_from_gif(queue: Queue, job: Job, args: dict, meta: JobMeta):
    """
    Queue worker that creates an AVIF version of a GIF file using ffmpeg.

    Args:
        args: Dict containing indexed_file_id
        meta: JobMeta with job metadata
    """
    logger.info(f"Creating AVIF for {args}")
    indexed_file_id = args["indexed_file_id"]
    try:
        indexed_file = IndexedFile.objects.get(id=indexed_file_id)
    except ObjectDoesNotExist:
        logger.info(f"IndexedFile {indexed_file_id} not found")
        return

    if indexed_file.derived_files.filter(mime_type="image/avif").exists():
        print(f"AVIF already exists for {indexed_file.path}")
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(settings.MEDIA_ROOT) / indexed_file.path
        stem = Path(indexed_file.path).stem
        output_path = Path(temp_dir) / f"{stem}.avif"
        if not output_path.exists():
            try:
                run_subprocess(
                    [
                        "ffmpeg",
                        "-i",
                        input_path,
                        "-vf",
                        "pad=iw+mod(iw\\,2):ih+mod(ih\\,2):0:0:black",
                        "-c:v",
                        "libsvtav1",
                        output_path,
                    ]
                    # ["ffmpeg", "-i", input_path, "-c:v", "libaom-av1", output_path]
                )
            except SubprocessError as ee:
                print(ee)
                return None

        result = IndexedFile.objects.get_or_create_from_file(
            output_path, derived_from=indexed_file, derived_for="compression"
        )
        logger.info(f"Created AVIF for {indexed_file.path}")
        return result


@task(media_analysis_queue)
def generate_video_thumbnail(queue: Queue, job: Job, args: dict, meta: JobMeta):
    """Generate thumbnail for a video file.

    Args:
        args: Dict containing indexed_file_id
    """
    from fileindex.services import media_analysis

    indexed_file_id = args["indexed_file_id"]
    logger.info(f"Generating video thumbnail for {indexed_file_id}")

    try:
        indexed_file = IndexedFile.objects.get(pk=indexed_file_id)
    except ObjectDoesNotExist:
        logger.error(f"IndexedFile {indexed_file_id} not found")
        return

    # Check if thumbnail already exists
    if indexed_file.derived_files.filter(derived_for="thumbnail").exists():
        logger.info(f"Thumbnail already exists for video {indexed_file_id}")
        return

    # Generate thumbnail
    try:
        thumbnail_path = media_analysis.generate_video_thumbnail(indexed_file.file.path)
        if thumbnail_path:
            try:
                # Create IndexedFile for thumbnail in one step
                thumb_indexedfile, _ = IndexedFile.objects.get_or_create_from_file(
                    thumbnail_path, derived_from=indexed_file, derived_for="thumbnail"
                )
                logger.info(f"Generated thumbnail for video {indexed_file_id}")
            finally:
                # Always clean up temp file
                with contextlib.suppress(OSError):
                    Path(thumbnail_path).unlink()
    except Exception as e:
        logger.error(f"Failed to generate thumbnail for {indexed_file_id}: {e}")
