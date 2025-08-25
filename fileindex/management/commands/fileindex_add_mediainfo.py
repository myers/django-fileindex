"""
Management command to add MediaInfo metadata to existing IndexedFile records.

This command backfills MediaInfo metadata for files that were indexed before
the MediaInfo integration was added.
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from tqdm import tqdm

from fileindex.models import IndexedFile
from fileindex.services import mediainfo_analysis

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Add MediaInfo metadata to existing IndexedFile records"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-extraction even if mediainfo key already exists'
        )
        parser.add_argument(
            '--mime-type',
            type=str,
            help='Only process files with this MIME type (e.g., video/quicktime)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of files to process in each batch (default: 100)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of files to process (for testing)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        force = options['force']
        mime_type = options['mime_type']
        batch_size = options['batch_size']
        limit = options['limit']
        dry_run = options['dry_run']

        # Check if MediaInfo is available
        if not mediainfo_analysis.is_pymediainfo_available():
            raise CommandError(
                "MediaInfo (pymediainfo) is not available. "
                "Install it with: pip install pymediainfo"
            )

        # Build query
        queryset = IndexedFile.objects.all()
        
        # Filter by MIME type if specified
        if mime_type:
            queryset = queryset.filter(mime_type=mime_type)
            self.stdout.write(f"Filtering by MIME type: {mime_type}")
        
        # Filter out files that already have mediainfo unless force is specified
        if not force:
            queryset = queryset.exclude(metadata__has_key='mediainfo')
            self.stdout.write("Excluding files that already have mediainfo metadata")
        
        # Apply limit if specified
        if limit:
            queryset = queryset[:limit]
            self.stdout.write(f"Limited to first {limit} files")
        
        total_files = queryset.count()
        
        if total_files == 0:
            self.stdout.write(self.style.SUCCESS("No files to process"))
            return
        
        self.stdout.write(f"Found {total_files} files to process")
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS("DRY RUN - No changes will be made"))
            # Show a sample of files that would be processed
            sample_files = queryset[:5]
            for indexed_file in sample_files:
                self.stdout.write(f"  Would process: {indexed_file.file.name} ({indexed_file.mime_type})")
            if total_files > 5:
                self.stdout.write(f"  ... and {total_files - 5} more files")
            return
        
        # Process files in batches
        processed = 0
        errors = 0
        
        # Use tqdm for progress bar
        with tqdm(total=total_files, desc="Processing files") as pbar:
            # Process in batches to avoid loading all files into memory
            while processed < total_files:
                batch = queryset[processed:processed + batch_size]
                
                with transaction.atomic():
                    for indexed_file in batch:
                        try:
                            self._process_file(indexed_file, force)
                            processed += 1
                            pbar.update(1)
                        
                        except Exception as e:
                            errors += 1
                            logger.error(f"Failed to process {indexed_file.file.name}: {e}")
                            self.stderr.write(f"Error processing {indexed_file.file.name}: {e}")
                            pbar.update(1)
                            processed += 1
                
                # Break if we've processed all files
                if processed >= total_files:
                    break
        
        # Report results
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCompleted processing {total_files} files:\n"
                f"  Successfully processed: {processed - errors}\n"
                f"  Errors: {errors}"
            )
        )
        
        if errors > 0:
            self.stdout.write(
                self.style.WARNING(
                    "Some files had errors. Check the logs for details."
                )
            )

    def _process_file(self, indexed_file: IndexedFile, force: bool):
        """Process a single IndexedFile to add MediaInfo metadata.
        
        Args:
            indexed_file: The IndexedFile instance to process
            force: Whether to force re-extraction if mediainfo already exists
        """
        # Check if file already has mediainfo metadata and force is not specified
        if not force and indexed_file.metadata and 'mediainfo' in indexed_file.metadata:
            logger.debug(f"Skipping {indexed_file.file.name} - already has mediainfo metadata")
            return
        
        # Get the file path
        file_path = indexed_file.file.path
        
        # Extract MediaInfo metadata based on MIME type
        mediainfo_data = None
        
        if indexed_file.mime_type and indexed_file.mime_type.startswith("video/"):
            mediainfo_data = mediainfo_analysis.get_mediainfo_for_video(file_path)
        elif indexed_file.mime_type and indexed_file.mime_type.startswith("audio/"):
            mediainfo_data = mediainfo_analysis.get_mediainfo_for_audio(file_path)
        elif indexed_file.mime_type and indexed_file.mime_type.startswith("image/"):
            mediainfo_data = mediainfo_analysis.get_mediainfo_for_image(file_path)
        
        # Only update if we got metadata
        if mediainfo_data:
            # Ensure metadata dict exists
            if indexed_file.metadata is None:
                indexed_file.metadata = {}
            
            # Add mediainfo data
            indexed_file.metadata['mediainfo'] = mediainfo_data
            
            # Save the changes
            indexed_file.save(update_fields=['metadata'])
            
            logger.info(f"Added MediaInfo metadata to {indexed_file.file.name}")
        else:
            logger.warning(f"No MediaInfo metadata extracted for {indexed_file.file.name}")