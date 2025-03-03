from django.core.management.base import BaseCommand
from semantis_app.models import Judgment
from semantis_app.utils.metadata import MetadataParser
import time
from django.db import transaction

class Command(BaseCommand):
    help = 'Update all judgments with improved title-based metadata extraction'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of judgments to process in each batch (default: 50)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes'
        )
        parser.add_argument(
            '--court',
            type=str,
            help='Filter judgments by court code (e.g., ZASCA)'
        )

    def handle(self, *args, **options):
        batch_size = options.get('batch_size')
        dry_run = options.get('dry_run')
        court = options.get('court')
        
        # Build query
        query = {}
        if court:
            query['court'] = court
        
        judgments = Judgment.objects.filter(**query)
        total_judgments = judgments.count()
        
        if total_judgments == 0:
            self.stdout.write("No judgments found that match the criteria.")
            return

        self.stdout.write(f"Found {total_judgments} judgments to process")
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN: Would update metadata for {total_judgments} judgments"
            ))
            return

        # Start processing
        start_time = time.time()
        total_processed = 0
        total_updated = 0
        batch_number = 1
        
        while True:
            batch_start = (batch_number - 1) * batch_size
            batch_end = batch_start + batch_size
            batch_judgments = judgments[batch_start:batch_end]
            
            if not batch_judgments:
                break

            self.stdout.write(f"\nProcessing batch {batch_number}...")
            
            with transaction.atomic():
                batch_updated = 0
                for judgment in batch_judgments:
                    # Process metadata from title
                    if judgment.title:
                        parser = MetadataParser(judgment.text_markdown, judgment.title)
                        metadata = parser.parse_title()
                        
                        # Check which fields should be updated
                        updated = False
                        for field, value in metadata.items():
                            if value and hasattr(judgment, field):
                                current_value = getattr(judgment, field)
                                if not current_value or (field in ['court', 'neutral_citation_year', 'neutral_citation_number']):
                                    setattr(judgment, field, value)
                                    updated = True
                                    self.stdout.write(f"  Updated {field}: {value} for {judgment.title[:50]}...")
                        
                        # Save if updated
                        if updated:
                            judgment.save()
                            batch_updated += 1
            
                total_processed += len(batch_judgments)
                total_updated += batch_updated
            
            # Update progress
            elapsed_time = time.time() - start_time
            avg_time = elapsed_time / total_processed if total_processed > 0 else 0
            progress = (total_processed / total_judgments) * 100
            
            self.stdout.write(
                f"Progress: {progress:.1f}% ({total_processed}/{total_judgments})\n"
                f"Updated in this batch: {batch_updated}\n"
                f"Total updated: {total_updated}\n"
                f"Average time per judgment: {avg_time:.2f} seconds\n"
                f"Elapsed time: {elapsed_time:.2f} seconds"
            )
            
            batch_number += 1
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(
            f"\nCompleted processing {total_processed} judgments\n"
            f"Total updated: {total_updated}\n"
            f"Total time: {time.time() - start_time:.2f} seconds"
        )) 