# django-fileindex

A Django app for file deduplication and indexing using SHA hashes. This app helps manage files by creating a content-addressable storage system that prevents duplicate files and tracks file metadata.

## Features

- **File Deduplication**: Uses SHA-512 hashing to identify and prevent duplicate file storage
- **Smart File Storage**: Organizes files in a content-addressable structure
- **Image Processing**:
  - Automatic thumbhash generation for images
  - Image dimension extraction
  - AVIF conversion for GIF files
- **File Tracking**: Tracks multiple file paths pointing to the same content
- **Background Processing**: Uses django-pg-queue for asynchronous tasks
- **File Watching**: Automatically import new files from watched directories
- **Admin Interface**: Django admin integration for managing indexed files

## Installation

```bash
pip install django-fileindex
```

## Configuration

1. Add `fileindex` to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    'fileindex.apps.FileindexAppConfig',
    'pgq',  # Required for background tasks
    ...
]
```

2. Include the fileindex URLs:

```python
from django.urls import path, include

urlpatterns = [
    ...
    path('fileindex/', include('fileindex.urls')),
    ...
]
```

3. Configure file serving (optional):

```python
# For X-Sendfile support
SENDFILE_BACKEND = 'django_sendfile.backends.nginx'
SENDFILE_ROOT = MEDIA_ROOT
```

4. Run migrations:

```bash
python manage.py migrate fileindex
```

## Usage

### File Upload Handling in Forms

Django-fileindex provides custom form fields and mixins for easy file upload handling:

```python
from fileindex import IndexedFileField, IndexedFileModelForm

# Simple form with file upload
class DocumentForm(forms.Form):
    file = IndexedFileField(
        allowed_extensions=['.pdf', '.doc'],
        max_file_size=10 * 1024 * 1024  # 10MB
    )

# ModelForm with automatic IndexedFile creation
class ImageForm(IndexedFileModelForm):
    class Meta:
        model = MyModel
        fields = ['title', 'description']

    indexed_file_field_name = 'image'  # Field on model that stores IndexedFile
```

See [File Upload Documentation](docs/file-uploads.md) for detailed examples and best practices.

### File Import Service

The file import service provides programmatic access to file indexing:

```python
from fileindex.services.file_import import import_file, batch_import_files

# Import a single file
indexed_file, created, error = import_file('/path/to/file.jpg')

# Import multiple files in batch
stats = batch_import_files(
    ['/path/to/file1.jpg', '/path/to/file2.png'],
    delete_after=True  # Delete originals after import
)
```

### Management Commands

```bash
# Add files to the index
python manage.py fileindex_add /path/to/file1 /path/to/directory

# Watch directories for new files
python manage.py fileindex_watch /path/to/directory --remove-after-import

# Create AVIF versions of GIF files
python manage.py fileindex_create_avif_for_gif

# Populate missing metadata for existing files (includes MediaInfo)
python manage.py fileindex_populate_missing_metadata

# Populate MediaInfo for specific file types only
python manage.py fileindex_populate_missing_metadata --mime-type video/quicktime

# Run background worker for processing tasks
python manage.py worker
```

### Basic File Operations

```python
from fileindex.models import IndexedFile

# Index a file from the filesystem
indexed_file, created = IndexedFile.objects.get_or_create_from_file('/path/to/file.jpg')

# Access file information
print(f"SHA-512: {indexed_file.sha512}")
print(f"Size: {indexed_file.size}")
print(f"MIME type: {indexed_file.mime_type}")
print(f"Storage path: {indexed_file.path}")
```

### Image Processing

Images are automatically processed to extract dimensions and generate thumbhashes:

```python
from fileindex.models import IndexedImage

# Get or create an indexed image
indexed_image, created = IndexedImage.objects.get_or_create_from_indexedfile(indexed_file)

print(f"Dimensions: {indexed_image.width}x{indexed_image.height}")
print(f"Thumbhash: {indexed_image.thumbhash}")
```

## Development

### Running Tests

The project supports both SQLite and PostgreSQL for testing:

```bash
# Run tests with SQLite (default)
USE_POSTGRES=false uv run pytest --cov=fileindex

# Run tests with PostgreSQL (requires Docker)
./test_with_postgres.sh

# Or manually with docker-compose
docker-compose up -d
DJANGO_SETTINGS_MODULE=tests.settings_postgres uv run pytest --cov=fileindex
docker-compose down
```

### Setting up development environment

```bash
# Clone the repository
git clone https://github.com/yourusername/django-fileindex.git
cd django-fileindex

# Install with UV
uv sync

# Run tests
uv run pytest --cov=fileindex --cov-report=html

# View coverage report
open htmlcov/index.html

# Make new migrations
uv run python -m django makemigrations fileindex --settings=tests.settings
```

### Releasing new versions

```bash
# The release script automates version bumping and tagging
bin/release

# This will:
# 1. Check for uncommitted changes
# 2. Bump the patch version (e.g., 0.7.3 -> 0.7.4)
# 3. Commit the version change
# 4. Create an annotated git tag
# 5. Show commands to push the release

# After running bin/release, push the changes:
git push origin main --tags

# Or push separately:
git push origin main
git push origin v0.7.4  # Use the actual new version number
```

## Models

### IndexedFile

The main model for storing file information:
- `size`: File size in bytes
- `sha1`: SHA-1 hash (optional)
- `sha512`: SHA-512 hash (primary identifier)
- `mime_type`: MIME type of the file
- `file`: Django FileField pointing to the stored file
- `first_seen`: Timestamp when first indexed
- `corrupt`: Flag for corrupted files
- `derived_from`: Reference to source file (for converted files)

### IndexedImage

Additional metadata for image files:
- `indexedfile`: One-to-one relation to IndexedFile
- `thumbhash`: Compact representation of the image
- `width`: Image width in pixels
- `height`: Image height in pixels

### FilePath

Tracks all file paths that point to an indexed file:
- `indexedfile`: Foreign key to IndexedFile
- `path`: Original file path
- `mtime`: Modification time
- `ctime`: Creation time
- `hostname`: Hostname where file was found

## Services

### Metadata Extraction

The metadata extraction system uses multiple tools to extract comprehensive metadata:

- **FFprobe**: Primary tool for video/audio analysis (ffmpeg required)
- **MediaInfo**: Enhanced metadata extraction, especially for professional formats like DV
- **Pillow**: Image processing and thumbnail generation

#### Metadata Structure

```json
{
  "width": 720,              // from ffprobe (trusted)
  "height": 480,             // from ffprobe (trusted) 
  "duration": 5000,          // from ffprobe (trusted)
  "ffprobe": {               // complete ffprobe output
    "version": "4.4.2",
    "data": {...}
  },
  "mediainfo": {             // complete MediaInfo output (NEW)
    "version": "21.09",
    "tracks": [
      {
        "track_type": "General",
        "recorded_date": "2004-10-04 14:43:30",  // DV recording date
        "duration": 5000
      },
      {
        "track_type": "Video",
        "commercial_name": "DVCPRO",             // DV format
        "timecode": "00:00:00;06",               // SMPTE timecode
        "scan_type": "Interlaced",
        "width": 720,
        "height": 480
      }
    ]
  }
}
```

#### DV-Specific Metadata

For DV files, MediaInfo provides critical information not available from ffprobe:

- **Recording Date**: Actual date/time when footage was recorded (not file creation date)
- **SMPTE Timecode**: Frame-accurate timecode information
- **Commercial Format**: Specific DV variant (DVCPRO, DVCAM, MiniDV)
- **Camera Settings**: White balance, focus mode, etc.
- **Field Order**: Interlacing information (BFF/TFF)

### File Import Service

Located in `fileindex.file_import_service`, provides:
- `should_import_file()`: Check if a file should be imported
- `import_single_file()`: Import a single file
- `import_directory()`: Import all files in a directory
- `import_paths()`: Import from multiple paths

### Watch Service

Located in `fileindex.watch_service`, provides:
- `FileImportEventHandler`: Event handler for file system events
- `create_file_watcher()`: Create a configured file watcher
- `watch_and_import()`: Watch directories and import files

## Signals

- `indexedfile_added`: Fired when a new file is indexed
- `indexedimage_added`: Fired when image metadata is generated

## Requirements

All Python dependencies are managed in `pyproject.toml`. Install with `uv sync` or `pip install -e .`

### External Tools

- **ffmpeg/ffprobe**: Required for video/audio metadata extraction
- **MediaInfo**: Optional but recommended for professional video formats (DV, etc.)
  - Linux: `apt install mediainfo`  
  - macOS: `brew install mediainfo`
  - Windows: Download from MediaArea website
- watchdog >= 3.0.0
- PostgreSQL (for django-pg-queue)

## License

This project is licensed under the MIT License.
