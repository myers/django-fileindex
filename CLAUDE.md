# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

django-fileindex is a Django application for file deduplication and indexing using SHA-512 hashes. It implements a content-addressable storage system that prevents duplicate files and tracks file metadata.

## Development Commands

### Testing
```bash
# Run all tests with coverage (uses PostgreSQL via Docker)
uv run pytest --cov=fileindex --cov-report=html -v

# Run specific test file
uv run pytest tests/test_models.py -v

# Run tests matching a pattern
uv run pytest -k "test_import" -v

# Quick test run (no coverage)
uv run pytest
```

### Code Quality
```bash
# Run all pre-commit hooks
pre-commit run --all-files
```

## Architecture

### Core Models (fileindex/models.py)

- **IndexedFile**: Main model storing file metadata (SHA-512 hash, size, MIME type). Uses content-addressable storage where files are stored by their hash.
- **FilePath**: Tracks all file paths pointing to an IndexedFile (many-to-one relationship)
- **Metadata**: Stored as JSON fields on IndexedFile - includes ImageMetadata, VideoMetadata, AudioMetadata

### Service Layer (fileindex/services/)

- **file_import.py**: Core import logic for adding files to the index
- **watch.py**: File system watching using watchdog library
- **metadata_extraction.py**: Extracts metadata from media files (dimensions, thumbhash, duration)
- **file_validation.py**: Validation rules for importing files
- **media_analysis.py**: Media file analysis utilities

### Form Integration (fileindex/forms.py, fields.py)

- **IndexedFileField**: Custom form field for file uploads with validation
- **IndexedFileModelForm**: Mixin for ModelForms that automatically creates IndexedFile entries
- **upload_utils.py**: Helper functions for handling file uploads

### Management Commands

Located in fileindex/management/commands/:
- **fileindex_add.py**: Import files from command line
- **fileindex_watch.py**: Watch directories for new files
- **fileindex_backup_orphaned.py**: Backup orphaned files
- **fileindex_populate_missing_metadata.py**: Generate missing metadata

## Testing Approach

- Uses pytest with pytest-django
- PostgreSQL required for tests (automatically started via docker-compose in conftest.py)
- Test database configured at port 8732 to avoid conflicts
- Factory classes in fileindex/factories.py for test data generation
- Fixtures in tests/utils.py for common test scenarios

## Key Implementation Details

### File Storage
- Files stored in MEDIA_ROOT with structure: `{prefix}/{sha512[:2]}/{sha512[2:4]}/{sha512}`
- SHA-512 used as primary identifier (unique constraint)
- Hard linking supported to avoid duplicates

### Metadata Extraction
- Images: Automatic thumbhash generation, dimension extraction
- Videos: Duration, frame rate, dimensions
- Audio: Duration extraction
- Metadata stored as JSON in `metadata` field

### Import Process
1. Calculate SHA-512 hash
2. Check if file already indexed
3. Copy/hard link to storage location
4. Extract metadata based on MIME type
5. Create FilePath entry for original location

## Dependencies

Core dependencies managed via pyproject.toml:
- Django >= 5.2
- Pillow with AVIF support for image processing
- thumbhash-python for image blur hashes
- watchdog for file system monitoring
- tqdm for progress bars

## Database

PostgreSQL required for development and testing. Test configuration:
- Host: localhost
- Port: 8732
- Database: fileindex_test
- User/Password: fileindex/fileindex
