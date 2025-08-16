from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import FilePath, IndexedFile


def format_file_size(size_bytes):
    """Utility function to format file size in human readable format."""
    if not size_bytes:
        return "-"

    size = float(size_bytes)  # Use local copy to avoid mutating original
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_sha512_short(sha512):
    """Utility function to format SHA512 hash as short display string."""
    return f"{sha512[:10]}..." if sha512 else "-"


class FilePathInline(admin.TabularInline):
    model = FilePath
    extra = 0
    max_num = 10  # Limit to prevent memory issues
    readonly_fields = ["path", "mtime", "ctime", "hostname", "created_at"]
    fields = ["path", "mtime", "ctime", "hostname", "created_at"]
    ordering = ["-created_at"]
    verbose_name = "File Path"
    verbose_name_plural = "File Paths"

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False




class DerivedFileInline(admin.TabularInline):
    model = IndexedFile
    fk_name = "derived_from"
    extra = 0
    max_num = 5  # Limit to prevent memory issues
    readonly_fields = [
        "sha512_short",
        "derived_for",
        "mime_type",
        "size_formatted",
        "first_seen",
    ]
    fields = [
        "sha512_short",
        "derived_for",
        "mime_type",
        "size_formatted",
        "first_seen",
    ]
    ordering = ["-first_seen"]
    verbose_name = "Derived File"
    verbose_name_plural = "Derived Files"

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def sha512_short(self, obj):
        return format_sha512_short(obj.sha512)

    sha512_short.short_description = "SHA512"

    def size_formatted(self, obj):
        return format_file_size(obj.size)

    size_formatted.short_description = "Size"


@admin.register(IndexedFile)
class IndexedFileAdmin(admin.ModelAdmin):
    list_display = [
        "sha512_short",
        "mime_type",
        "size_formatted",
        "first_seen",
        "corrupt_status",
    ]
    list_filter = ["mime_type", "corrupt", "derived_for"]
    search_fields = ["sha512", "sha1"]
    list_per_page = 50  # Optimize page size for performance
    inlines = [
        FilePathInline,
        DerivedFileInline,
    ]

    class Media:
        css = {"all": ("admin/css/fileindex_admin.css",)}

    def get_queryset(self, request):
        """Optimize queryset to reduce database queries."""
        qs = super().get_queryset(request)
        return qs.select_related("derived_from").prefetch_related(
            "derived_files", "filepath_set"
        )

    def get_readonly_fields(self, request, obj=None):
        # Make ALL fields readonly for this admin
        return [f.name for f in self.model._meta.fields] + [
            "size_formatted",
            "file_url",
        ]

    def has_add_permission(self, request):
        return False  # Disable adding new files

    def has_delete_permission(self, request, obj=None):
        return False  # Disable deleting files

    def sha512_short(self, obj):
        return format_sha512_short(obj.sha512)

    sha512_short.short_description = "SHA512"

    def size_formatted(self, obj):
        return format_file_size(obj.size)

    size_formatted.short_description = "Size"

    def corrupt_status(self, obj):
        if obj.corrupt is True:
            return format_html(
                '<span class="corrupt-status corrupt-status--error">CORRUPT</span>'
            )
        elif obj.corrupt is False:
            return format_html(
                '<span class="corrupt-status corrupt-status--success">OK</span>'
            )
        return format_html(
            '<span class="corrupt-status corrupt-status--warning">Unknown</span>'
        )

    corrupt_status.short_description = "Status"

    def file_url(self, obj):
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank">{}</a>', obj.url, obj.file.name
            )
        return "-"

    file_url.short_description = "File URL"
