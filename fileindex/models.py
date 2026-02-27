import datetime
import logging
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from django.conf import settings
from django.db import models
from django.dispatch import Signal
from django.utils import timezone

from fileindex import fileutils

logger = logging.getLogger(__name__)

local_tz = timezone.get_current_timezone()


# TypedDict definitions for metadata structure
class BaseMetadata(TypedDict):
    """Base metadata fields that can be present for any file type.

    All fields use NotRequired since metadata extraction might fail or be incomplete.
    """


class ImageInfo(TypedDict):
    """Image-specific fields nested under the 'image' key."""

    width: int
    height: int
    thumbhash: str
    animated: NotRequired[bool]  # True if animated (GIF/WEBP/AVIF)


class ImageMetadata(TypedDict):
    """Metadata structure for image files.

    Fields:
    - image: Nested image info (width, height, thumbhash, animated)
    - duration: Animation duration in milliseconds (only for animated images)
    """

    image: ImageInfo
    duration: NotRequired[int]  # Only present for animated images (in milliseconds)


class VideoStreamInfo(TypedDict):
    """Video stream information from ffprobe."""

    codec: NotRequired[str]  # Video codec name (e.g., 'h264', 'hevc')
    width: NotRequired[int]
    height: NotRequired[int]
    frame_rate: NotRequired[float]
    bitrate: NotRequired[int]


class AudioStreamInfo(TypedDict):
    """Audio stream information from ffprobe."""

    codec: NotRequired[str]  # Audio codec name (e.g., 'aac', 'mp3')
    bitrate: NotRequired[int]
    sample_rate: NotRequired[int]
    channels: NotRequired[int]
    tags: NotRequired[dict[str, str]]  # Title, artist, album metadata


class MediaInfoMetadata(TypedDict):
    """Filtered MediaInfo metadata (supplemental to ffprobe)."""

    version: str
    general: NotRequired[dict[str, Any]]
    video: NotRequired[dict[str, Any]]
    audio_streams: NotRequired[list[dict[str, Any]]]


class VideoMetadata(TypedDict):
    """Metadata structure for video files.

    Required fields:
    - duration: Video length in milliseconds
    - video: Video stream info (codec, width, height, frame_rate, bitrate)

    Optional:
    - audio: Audio stream information including codec
    - ffprobe: Complete ffprobe output with version info
    - mediainfo: Filtered MediaInfo metadata
    """

    duration: int  # in milliseconds
    video: VideoStreamInfo
    audio: NotRequired[AudioStreamInfo]
    ffprobe: NotRequired[dict[str, Any]]
    mediainfo: NotRequired[MediaInfoMetadata]


class AudioMetadata(TypedDict):
    """Metadata structure for audio files.

    Required fields:
    - duration: Audio length in milliseconds

    Optional:
    - audio: Audio stream information including codec and tags
    - ffprobe: Complete ffprobe output with version info
    - mediainfo: Filtered MediaInfo metadata
    """

    duration: int  # in milliseconds
    audio: NotRequired[AudioStreamInfo]
    ffprobe: NotRequired[dict[str, Any]]
    mediainfo: NotRequired[MediaInfoMetadata]


# Union type for all possible metadata structures
FileMetadata = ImageMetadata | VideoMetadata | AudioMetadata | BaseMetadata


indexedfile_added = Signal()


def filepath_nfo_from_file(filepath):
    path = Path(filepath).resolve()
    ret = {"path": str(path)}
    stat = path.stat()
    ret["mtime"] = datetime.datetime.fromtimestamp(stat.st_mtime, local_tz)
    ret["ctime"] = datetime.datetime.fromtimestamp(stat.st_ctime, local_tz)
    return ret


class IndexedFileManager(models.Manager):
    def get_or_create_with_filepath_nfo(
        self,
        filepath,
        only_hard_link=False,
        derived_from=None,
        derived_for=None,
        hash_progress_callback=None,
        **filepath_kwargs,
    ):
        nfo = fileutils.analyze_file(filepath, hash_progress_callback=hash_progress_callback)

        # Use SHA-512 as the lookup field (should be unique)
        # Everything else goes in defaults so they're only used for creation
        defaults = {
            "sha1": nfo["sha1"],
            "mime_type": nfo["mime_type"],
            "size": nfo["size"],
            "derived_from": derived_from,
            "first_seen": datetime.datetime.now(local_tz),
        }

        # Add derived_for if specified
        if derived_for is not None:
            defaults["derived_for"] = derived_for

        # Extract metadata BEFORE creating the object to satisfy constraints
        from fileindex.services.metadata import extract_metadata

        metadata, is_corrupt = extract_metadata(str(filepath), nfo["mime_type"])

        # Add the extracted metadata to defaults
        if metadata:
            defaults["metadata"] = metadata

        # Set corrupt flag if metadata extraction failed
        if is_corrupt:
            defaults["corrupt"] = True

        indexedfile, created = self.get_or_create(
            sha512=nfo["sha512"],
            defaults=defaults,
        )

        # Use path as the lookup field, other fields as defaults
        indexedfile.filepath_set.get_or_create(
            path=filepath_kwargs["path"],
            defaults={
                "mtime": filepath_kwargs["mtime"],
                "ctime": filepath_kwargs["ctime"],
                "created_at": datetime.datetime.now(local_tz),
            },
        )
        # Ensure MEDIA_ROOT is absolute to prevent files being created in wrong location
        media_root = Path(settings.MEDIA_ROOT).resolve()
        dest_path = media_root / indexedfile.path

        fileutils.smartadd(
            filepath,
            str(dest_path),
            only_hard_link=only_hard_link,
        )
        indexedfile.file.name = indexedfile.path

        # Metadata was already extracted before get_or_create for new files
        # No need to extract again

        indexedfile.save()

        # Only send signal after successful save with all metadata present
        # This ensures signal handlers have access to complete metadata
        if created:
            indexedfile_added.send(sender=indexedfile.__class__, instance=indexedfile)

        return indexedfile, created

    def get_or_create_from_file(
        self, filepath, only_hard_link=False, derived_from=None, derived_for=None, hash_progress_callback=None
    ):
        fp_nfo = filepath_nfo_from_file(str(filepath))
        return self.get_or_create_with_filepath_nfo(
            filepath,
            only_hard_link=only_hard_link,
            derived_from=derived_from,
            derived_for=derived_for,
            hash_progress_callback=hash_progress_callback,
            **fp_nfo,
        )


class IndexedFile(models.Model):
    objects = IndexedFileManager()

    size = models.BigIntegerField()  # Supports files larger than 2GB
    sha1 = models.CharField(max_length=255, db_index=True, null=True)
    sha512 = models.CharField(max_length=255, db_index=True, null=True, unique=True)
    mime_type = models.CharField(max_length=255, db_index=True, null=True)

    file = models.FileField(max_length=2048)
    first_seen = models.DateTimeField(null=False)

    corrupt = models.BooleanField(default=None, null=True)

    derived_from = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="derived_files",
    )

    # Type of derivation (null for original files, 'thumbnail' for video thumbnails)
    derived_for = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Type of derived file (e.g., 'thumbnail' for thumbnails)",
        choices=[
            (None, "Original file"),
            ("thumbnail", "Video thumbnail"),
            ("compression", "Compressed version (e.g., AVIF from GIF)"),
            # Future: ('preview', 'Document preview'),
            # ('transcoded', 'Transcoded video'), etc.
        ],
    )

    # Consolidated metadata field for type-specific data
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON field for type-specific metadata (dimensions, duration, etc.)",
    )

    class Meta:
        get_latest_by = "first_seen"
        indexes = [
            models.Index(fields=["derived_from", "derived_for"]),
            models.Index(fields=["derived_from", "mime_type"]),
        ]
        constraints = [
            # Images and videos must have dimensions (unless corrupt)
            # Supports both old flat structure and new nested structure
            models.CheckConstraint(
                condition=(
                    models.Q(corrupt__isnull=False, corrupt=True)  # Only skip if explicitly corrupt=True
                    | ~(models.Q(mime_type__startswith="image/") | models.Q(mime_type__startswith="video/"))
                    # Old flat structure (width/height at root)
                    | (models.Q(metadata__has_key="width") & models.Q(metadata__has_key="height"))
                    # New nested structure for images
                    | (
                        models.Q(mime_type__startswith="image/")
                        & models.Q(metadata__image__width__isnull=False)
                        & models.Q(metadata__image__height__isnull=False)
                    )
                    # New nested structure for videos
                    | (
                        models.Q(mime_type__startswith="video/")
                        & models.Q(metadata__video__width__isnull=False)
                        & models.Q(metadata__video__height__isnull=False)
                    )
                ),
                name="visual_media_requires_dimensions",
            ),
            # Audio and video must have duration (unless corrupt)
            models.CheckConstraint(
                condition=(
                    models.Q(corrupt__isnull=False, corrupt=True)  # Only skip if explicitly corrupt=True
                    | ~(models.Q(mime_type__startswith="audio/") | models.Q(mime_type__startswith="video/"))
                    | models.Q(metadata__has_key="duration")
                ),
                name="media_requires_duration",
            ),
            # Videos must have frame_rate (unless corrupt)
            # Supports both old flat structure and new nested structure
            models.CheckConstraint(
                condition=(
                    models.Q(corrupt__isnull=False, corrupt=True)  # Only skip if explicitly corrupt=True
                    | ~models.Q(mime_type__startswith="video/")
                    # Old flat structure
                    | models.Q(metadata__has_key="frame_rate")
                    # New nested structure
                    | models.Q(metadata__video__frame_rate__isnull=False)
                ),
                name="video_requires_frame_rate",
            ),
            # Animated images must have duration (unless corrupt)
            # Supports both old and new animated flag location
            models.CheckConstraint(
                condition=(
                    models.Q(corrupt__isnull=False, corrupt=True)  # Only skip if explicitly corrupt=True
                    # Old structure (animated at root)
                    | ~models.Q(metadata__animated=True)
                    # New structure (animated under image key)
                    | ~models.Q(metadata__image__animated=True)
                    | models.Q(metadata__has_key="duration")
                ),
                name="animated_requires_duration",
            ),
        ]

    @property
    def path(self):
        """
        Generate path for file storage.
        New structure: fileindex/XX/YY/HASH (no padding, no extension)
        """
        # Remove padding from hash
        hash_no_padding = self.sha512.rstrip("=")

        return str(
            Path("fileindex")
            / hash_no_padding[0:2]  # First level
            / hash_no_padding[2:4]  # Second level
            / hash_no_padding  # Filename (no extension)
        )

    @property
    def protected_url(self):
        """Return a protected URL that requires authentication."""
        # Return the actual media URL path
        return f"/media/{self.file.name}"

    @property
    def filename(self):
        first = self.filepath_set.first()
        if not first:
            raise ValueError("IndexedFile has no associated FilePath")
        return Path(first.path).name

    @property
    def url(self):
        # Return the actual media URL path
        return f"/media/{self.file.name}"

    def save(self, *args, **kwargs):
        if not self.first_seen:
            self.first_seen = datetime.datetime.now(local_tz)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sha512[0:10]}..."

    @property
    def thumbnail(self):
        """Get thumbnail if this is a video file"""
        if self.mime_type and self.mime_type.startswith("video/"):
            return self.derived_files.filter(derived_for="thumbnail").first()
        return None


# Signal receivers removed - apps should implement their own handlers for
# indexedfile_added signal


class FilePath(models.Model):
    indexedfile = models.ForeignKey(IndexedFile, null=False, on_delete=models.CASCADE)
    mtime = models.DateTimeField(null=False)
    ctime = models.DateTimeField(null=False)
    hostname = models.CharField(max_length=1024, null=True)
    path = models.CharField(max_length=2048, db_index=True, null=False)
    created_at = models.DateTimeField(null=False)

    class Meta:
        unique_together = [["indexedfile", "path"]]

    def __str__(self):
        return f"({self.pk}) {self.path!r}"

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = datetime.datetime.now(local_tz)
        return super().save(*args, **kwargs)
