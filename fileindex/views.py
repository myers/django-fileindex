import datetime
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Prefetch, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_list_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView
from django_rsgi.serve import serve_file as rsgi_serve_file

from .models import FilePath, IndexedFile
from .services.file_validation import should_import, should_import_filename

local_tz = timezone.get_current_timezone()


def serve_fileindex_media(request, path):
    """
    Serve fileindex media files with MIME type from database.
    Handles requests to /media/fileindex/<first2>/<next2>/<sha512_hash>
    SHA512 is stored as base32-encoded string with '=' padding in database,
    but files are stored extensionless with padding stripped.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Extract SHA512 from the path structure
    # Files are stored as fileindex/XX/XX/XXXXXXXXX (no extension) where X is base32
    path_parts = path.split("/")
    logger.debug(f"serve_fileindex_media: path={path}, path_parts={path_parts}")

    if len(path_parts) >= 3:
        # The filename is the SHA512 hash without padding (extensionless)
        filename = path_parts[-1]
        # In case there's still an extension (legacy), remove it
        hash_part = filename.split(".")[0]
        logger.debug(
            f"serve_fileindex_media: filename={filename}, hash_part={hash_part}"
        )

        # Try to find the IndexedFile - first with the hash as-is, then with padding
        indexed_file = None

        # Try exact match first (new extensionless format)
        try:
            indexed_file = IndexedFile.objects.get(sha512=hash_part)
            logger.debug(
                f"serve_fileindex_media: found IndexedFile with exact hash={hash_part}"
            )
        except IndexedFile.DoesNotExist:
            # Try with padding added (legacy format)
            padded_hash = hash_part
            while len(padded_hash) % 8 != 0:
                padded_hash += "="

            try:
                indexed_file = IndexedFile.objects.get(sha512=padded_hash)
                logger.debug(
                    f"serve_fileindex_media: found IndexedFile with padded hash={padded_hash}"
                )
            except IndexedFile.DoesNotExist:
                logger.warning(
                    f"serve_fileindex_media: IndexedFile not found for hash={hash_part} or padded={padded_hash}"
                )

        if indexed_file:
            full_path = f"fileindex/{path}"
            response = rsgi_serve_file(
                request,
                full_path,  # Full path under MEDIA_ROOT
                document_root=settings.MEDIA_ROOT,
            )
            # Override with MIME type from database
            if indexed_file.mime_type:
                response["Content-Type"] = indexed_file.mime_type
                logger.debug(
                    f"serve_fileindex_media: set Content-Type to {indexed_file.mime_type}"
                )

            # Force inline display for images to prevent download
            if indexed_file.mime_type and indexed_file.mime_type.startswith("image/"):
                response["Content-Disposition"] = "inline"
                logger.debug("serve_fileindex_media: set Content-Disposition to inline")

            return response

    # Return 404 if file not found in database or path doesn't match expected structure
    from django.http import Http404

    raise Http404("File not found")


@require_GET
def lookup(request):
    if not should_import_filename(request.GET["filename"]):
        return HttpResponseBadRequest("cannot import")
    files = get_list_or_404(
        IndexedFile, sha512=request.GET["sha512"], sha1=request.GET["sha1"]
    )
    if len(files) > 1:
        return render(request, "fileindex/lookup.html", {"files": files})
    return redirect("fileindex:detail", permanent=True, pk=files[0].pk)


TEMP_DIR = Path(settings.MEDIA_ROOT) / "fileindex_uploads"


@csrf_exempt
@require_POST
def add(request):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    filepath_nfo = {
        "path": request.POST["path"],
        "ctime": datetime.datetime.fromtimestamp(
            float(request.POST["ctime"]), local_tz
        ),
        "mtime": datetime.datetime.fromtimestamp(
            float(request.POST["mtime"]), local_tz
        ),
        "hostname": request.POST["hostname"],
    }
    if not should_import_filename(request.POST["path"]):
        return HttpResponse()
    with tempfile.NamedTemporaryFile(dir=TEMP_DIR, delete=False) as dst:
        for chunk in request.FILES["file"].chunks():
            dst.write(chunk)
        dst.flush()
        if not should_import(dst.name):
            return HttpResponseBadRequest("cannot import")
        indexedfile, created = IndexedFile.objects.get_or_create_with_filepath_nfo(
            dst.name, **filepath_nfo
        )
        return redirect("fileindex:detail", pk=indexedfile.pk)


class IndexedFileDetail(DetailView):
    context_object_name = "indexedfile"
    queryset = IndexedFile.objects.all()


@method_decorator(staff_member_required, name="dispatch")
class FilesWithoutMetadataView(ListView):
    """Staff-only view to browse IndexedFiles without metadata."""

    model = IndexedFile
    template_name = "fileindex/files_without_metadata.html"
    context_object_name = "files"
    paginate_by = 50

    def get_queryset(self):
        """Get files with empty metadata or missing required fields."""
        # Start with files that have empty metadata
        queryset = (
            IndexedFile.objects.filter(Q(metadata={}) | Q(metadata__isnull=True))
            .select_related("indexedimage", "indexedvideo", "indexedaudio")
            .prefetch_related(
                Prefetch(
                    "filepath_set", queryset=FilePath.objects.order_by("-created_at")
                ),
                "postfile_set__post__source",
                "postimage_set__post__source",
                "postvideo_set__post__source",
                "postaudio_set__post__source",
            )
            .order_by("-first_seen")
        )

        # Filter by mime type if requested
        mime_filter = self.request.GET.get("mime", "")
        if mime_filter:
            if mime_filter == "image":
                queryset = queryset.filter(mime_type__startswith="image/")
            elif mime_filter == "video":
                queryset = queryset.filter(mime_type__startswith="video/")
            elif mime_filter == "audio":
                queryset = queryset.filter(mime_type__startswith="audio/")
            else:
                queryset = queryset.filter(mime_type=mime_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add summary statistics
        total_without_metadata = IndexedFile.objects.filter(
            Q(metadata={}) | Q(metadata__isnull=True)
        ).count()

        # Breakdown by type
        images_without = IndexedFile.objects.filter(
            Q(metadata={}) | Q(metadata__isnull=True), mime_type__startswith="image/"
        ).count()

        videos_without = IndexedFile.objects.filter(
            Q(metadata={}) | Q(metadata__isnull=True), mime_type__startswith="video/"
        ).count()

        audio_without = IndexedFile.objects.filter(
            Q(metadata={}) | Q(metadata__isnull=True), mime_type__startswith="audio/"
        ).count()

        context.update(
            {
                "total_without_metadata": total_without_metadata,
                "images_without_metadata": images_without,
                "videos_without_metadata": videos_without,
                "audio_without_metadata": audio_without,
                "current_filter": self.request.GET.get("mime", ""),
            }
        )

        return context


@method_decorator(staff_member_required, name="dispatch")
class VideoMetadataIssuesView(ListView):
    """Staff-only view to investigate video metadata issues."""

    model = IndexedFile
    template_name = "fileindex/video_metadata_issues.html"
    context_object_name = "videos"
    paginate_by = 50

    def get_queryset(self):
        """Get video files with missing or incomplete metadata."""
        return (
            IndexedFile.objects.filter(mime_type__startswith="video/")
            .filter(
                Q(metadata__duration__isnull=True)
                | Q(metadata__width__isnull=True)
                | Q(metadata__height__isnull=True)
                | Q(metadata__frame_rate__isnull=True)
                | Q(metadata={})
            )
            .select_related("indexedvideo")
            .prefetch_related(
                Prefetch(
                    "filepath_set", queryset=FilePath.objects.order_by("-created_at")
                ),
                "postvideo_set__post__source",
                "postfile_set__post__source",
            )
            .order_by("-first_seen")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add video statistics
        total_videos = IndexedFile.objects.filter(
            mime_type__startswith="video/"
        ).count()
        videos_with_complete_metadata = (
            IndexedFile.objects.filter(
                mime_type__startswith="video/",
                metadata__duration__isnull=False,
                metadata__width__isnull=False,
                metadata__height__isnull=False,
                metadata__frame_rate__isnull=False,
            )
            .exclude(metadata={})
            .count()
        )

        videos_missing_duration = IndexedFile.objects.filter(
            mime_type__startswith="video/", metadata__duration__isnull=True
        ).count()

        context.update(
            {
                "total_videos": total_videos,
                "videos_with_complete_metadata": videos_with_complete_metadata,
                "videos_with_issues": total_videos - videos_with_complete_metadata,
                "videos_missing_duration": videos_missing_duration,
            }
        )

        return context
