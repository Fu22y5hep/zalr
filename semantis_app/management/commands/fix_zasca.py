from django.core.management.base import BaseCommand
from semantis_app.models import Judgment
import time


class Command(BaseCommand):
    help = 'Fix court metadata for ZASCA judgments'

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

    def handle(self, *args, **options):
        batch_size = options.get('batch_size')
        dry_run = options.get('dry_run')

        # Get all ZASCA judgments with missing court field
        zasca_judgments = Judgment.objects.filter(
            saflii_url__contains='ZASCA',
            court__isnull=True
        )
        
        total_judgments = zasca_judgments.count()
        
        if total_judgments == 0:
            self.stdout.write("No ZASCA judgments found with missing court metadata.")
            return

        self.stdout.write(f"Found {total_judgments} ZASCA judgments with missing court metadata")
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN: Would set court='ZASCA' for {total_judgments} judgments"
            ))
            return

        # Start processing
        start_time = time.time()
        total_processed = 0
        batch_number = 1
        
        while True:
            batch_start = (batch_number - 1) * batch_size
            batch_end = batch_start + batch_size
            batch_judgments = zasca_judgments[batch_start:batch_end]
            
            if not batch_judgments:
                break

            self.stdout.write(f"\nProcessing batch {batch_number}...")
            
            for judgment in batch_judgments:
                # Update court field
                judgment.court = 'ZASCA'
                
                # Update citation year and number if missing
                citation_match = judgment.full_citation
                if citation_match and not judgment.neutral_citation_year:
                    try:
                        year = int(judgment.neutral_citation_year) if judgment.neutral_citation_year else None
                        number = int(judgment.neutral_citation_number) if judgment.neutral_citation_number else None
                        
                        if not year or not number:
                            judgment.neutral_citation_year = 0  # Placeholder, will be fixed by metadata processor
                            judgment.neutral_citation_number = 0  # Placeholder, will be fixed by metadata processor
                    except:
                        pass
                
                judgment.save()
                total_processed += 1
            
            # Update progress
            elapsed_time = time.time() - start_time
            avg_time = elapsed_time / total_processed if total_processed > 0 else 0
            progress = (total_processed / total_judgments) * 100
            
            self.stdout.write(
                f"Progress: {progress:.1f}% ({total_processed}/{total_judgments})\n"
                f"Average time per judgment: {avg_time:.2f} seconds\n"
                f"Elapsed time: {elapsed_time:.2f} seconds"
            )
            
            batch_number += 1
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(
            f"\nCompleted updating {total_processed} ZASCA judgments\n"
            f"Total time: {time.time() - start_time:.2f} seconds"
        )) 