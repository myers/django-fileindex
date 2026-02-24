# django-fileindex

A Django app for file deduplication and indexing. It implements a content-addressable storage system that prevents duplicate files and tracks file metadata.

## Why?

I built this as part of a larger system to manage my family's photos, videos, documents, and digital archives. Over the years, files ended up scattered across old hard drives, cloud services, SD cards, and USB sticks — with copies of copies everywhere and no easy way to know what I actually had. On top of that, I've been digitizing old MiniDV camcorder tapes and wanted to preserve the original recording dates and timecodes baked into the DV stream (which is why MediaInfo support exists).

django-fileindex is the piece that answers "have I seen this file before?" and "where did I find it?" — so I can throw files at it from any source without worrying about duplicates piling up.

**PostgreSQL only** — no effort has been made to support other databases.

## Features

- **File Deduplication**: SHA-512 hashing identifies and prevents duplicate file storage
- **Content-Addressable Storage**: Files organized by hash for efficient retrieval
- **Metadata Extraction**: Automatic extraction of image dimensions, video/audio duration, frame rates, and thumbhashes
- **Optional MediaInfo Support**: Enhanced metadata for professional formats like DV (recording dates, timecodes)
- **File Watching**: Monitor directories and automatically import new files
- **Form Integration**: Custom form fields and ModelForm mixin for file uploads
- **Admin Interface**: Read-only admin with file path tracking and metadata display

## Installation

```bash
pip install django-fileindex
```

For enhanced video metadata (DV recording dates, timecodes):

```bash
pip install django-fileindex[mediainfo]
```

## Quick Start

1. Add `fileindex` to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "fileindex",
]
```

2. Run migrations:

```bash
python manage.py migrate fileindex
```

## Usage

### Basic File Operations

```python
from fileindex.models import IndexedFile

# Index a file from the filesystem
indexed_file, created = IndexedFile.objects.get_or_create_from_file("/path/to/file.jpg")

# Access file information
print(f"SHA-512: {indexed_file.sha512}")
print(f"Size: {indexed_file.size}")
print(f"MIME type: {indexed_file.mime_type}")
print(f"Storage path: {indexed_file.path}")
```

### File Import Service

```python
from fileindex.services.file_import import import_file, batch_import_files

# Import a single file
indexed_file, created, error = import_file("/path/to/file.jpg")

# Import multiple files in batch
stats = batch_import_files(
    ["/path/to/file1.jpg", "/path/to/file2.png"],
    delete_after=True,  # Delete originals after import
)
```

### Management Commands

```bash
# Add files to the index
python manage.py fileindex_add /path/to/file1 /path/to/directory

# Watch directories for new files
python manage.py fileindex_watch /path/to/directory --remove-after-import

# Backup files no longer referenced by any FilePath
python manage.py fileindex_backup_orphaned

# Generate missing metadata for existing files
python manage.py fileindex_populate_missing_metadata
```

### Form Integration

```python
from fileindex.fields import IndexedFileField
from fileindex.forms import IndexedFileModelForm

# Simple form with file upload
class DocumentForm(forms.Form):
    file = IndexedFileField(
        allowed_extensions=[".pdf", ".doc"],
        max_file_size=10 * 1024 * 1024,  # 10MB
    )

# ModelForm with automatic IndexedFile creation
class ImageForm(IndexedFileModelForm):
    class Meta:
        model = MyModel
        fields = ["title", "description"]

    indexed_file_field_name = "image"
```

## Models

### IndexedFile

The main model for storing file information:

- `sha512`: SHA-512 hash (unique, primary identifier)
- `sha1`: SHA-1 hash (optional)
- `size`: File size in bytes
- `mime_type`: MIME type of the file
- `file`: FileField pointing to content-addressable storage
- `first_seen`: Timestamp when first indexed
- `corrupt`: Flag indicating metadata extraction failure
- `derived_from`: ForeignKey to source file (for thumbnails, conversions)
- `derived_for`: Type of derivation (`"thumbnail"`, `"compression"`, or None)
- `metadata`: JSONField with type-specific metadata (dimensions, duration, thumbhash, ffprobe/mediainfo output)

### FilePath

Tracks all file paths that point to an indexed file:

- `indexedfile`: ForeignKey to IndexedFile
- `path`: Original file path
- `mtime`: Last modification time
- `ctime`: Creation time
- `hostname`: Hostname where file was found

## Metadata Extraction

Metadata is stored as JSON in `IndexedFile.metadata` and varies by file type:

- **Images**: Width, height, thumbhash, animated detection
- **Video**: Width, height, duration, frame rate, codec info (via ffprobe)
- **Audio**: Duration, codec info (via ffprobe)
- **DV/Professional formats**: Recording date, timecode, format details (via optional MediaInfo)

## Signals

- `indexedfile_added`: Sent when a new IndexedFile is created and saved

## Development

```bash
git clone https://github.com/myers/django-fileindex.git
cd django-fileindex
uv sync
uv run pytest --cov=fileindex --cov-report=html -v
```

PostgreSQL is required for tests and is automatically started via Docker in the test configuration.

## External Tools

- **ffmpeg/ffprobe** (required for video/audio metadata):
  - macOS: `brew install ffmpeg`
  - Linux: `apt install ffmpeg`
- **MediaInfo** (optional, for DV and professional formats):
  - macOS: `brew install mediainfo`
  - Linux: `apt install mediainfo`

## License

MIT License. See [LICENSE](LICENSE) for details.
