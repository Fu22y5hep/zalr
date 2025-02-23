from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from semantis_app.utils.metadata import process_missing_metadata, MetadataParser
from semantis_app.models import Judgment
import sys
import time
from typing import List, Optional

class Command(BaseCommand):
    help = 'Process and extract metadata from judgments'

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
            '--continue-on-error',
            action='store_true',
            help='Continue processing if an error occurs with one judgment'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Process all judgments, even those with existing metadata'
        )
        parser.add_argument(
            '--fields',
            nargs='+',
            type=str,
            choices=['citation', 'court', 'case_number', 'date', 'judges', 'all'],
            default=['all'],
            help='Specific metadata fields to process (default: all)'
        )
        parser.add_argument(
            '--court',
            type=str,
            help='Filter judgments by court name'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress for each judgment'
        )

    def get_judgments_to_process(self, options) -> List[Judgment]:
        """Get the list of judgments that need processing based on options."""
        force = options.get('force')
        court = options.get('court')
        fields = options.get('fields')
        
        # Build the query based on missing fields
        if not force and 'all' not in fields:
            query = Q()
            if 'citation' in fields:
                query |= Q(full_citation__isnull=True)
            if 'court' in fields:
                query |= Q(court__isnull=True)
            if 'case_number' in fields:
                query |= Q(case_number__isnull=True)
            if 'date' in fields:
                query |= Q(judgment_date__isnull=True)
            if 'judges' in fields:
                query |= Q(judges__isnull=True)
        else:
            # Process all judgments if force is True
            query = Q()

        # Add court filter if specified
        if court:
            query &= Q(court__icontains=court)

        return Judgment.objects.filter(query)

    def process_judgment(self, judgment: Judgment, fields: List[str], verbose: bool) -> bool:
        """Process a single judgment's metadata."""
        if verbose:
            self.stdout.write(f"Processing {judgment.title[:100]}...")

        parser = MetadataParser(judgment.text_markdown, judgment.title)
        metadata = parser.extract_all()
        updated = False

        for field, value in metadata.items():
            if value and (fields == ['all'] or field in fields):
                old_value = getattr(judgment, field)
                if not old_value or old_value != value:
                    if verbose:
                        self.stdout.write(f"  Updated {field}: {value}")
                    setattr(judgment, field, value)
                    updated = True

        if updated:
            judgment.save()

        return updated

    def handle(self, *args, **options):
        batch_size = options.get('batch_size')
        dry_run = options.get('dry_run')
        continue_on_error = options.get('continue_on_error')
        verbose = options.get('verbose')
        fields = options.get('fields')

        try:
            # Get judgments to process
            judgments = self.get_judgments_to_process(options)
            total_judgments = judgments.count()
            
            if total_judgments == 0:
                self.stdout.write("No judgments found that need processing.")
                return

            self.stdout.write(f"Found {total_judgments} judgments to process")
            
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"DRY RUN: Would process metadata for {total_judgments} judgments"
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
                        try:
                            if self.process_judgment(judgment, fields, verbose):
                                batch_updated += 1
                        except Exception as e:
                            if continue_on_error:
                                self.stdout.write(self.style.WARNING(
                                    f"Error processing judgment {judgment.id}: {str(e)}"
                                ))
                            else:
                                raise
                    
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
                
                # Ask for continuation after each batch
                if not self.confirm_continue():
                    break
            
            # Final summary
            self.stdout.write(self.style.SUCCESS(
                f"\nCompleted processing {total_processed} judgments\n"
                f"Total updated: {total_updated}\n"
                f"Total time: {time.time() - start_time:.2f} seconds"
            ))

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nProcessing interrupted by user"))
            sys.exit(1)
        except Exception as e:
            if not continue_on_error:
                raise CommandError(f"Error processing metadata: {str(e)}")
            else:
                self.stdout.write(self.style.WARNING(f"Error occurred but continuing: {str(e)}"))

    def confirm_continue(self) -> bool:
        """Ask user if they want to continue processing"""
        self.stdout.write("\nContinue processing next batch? [y/N] ")
        try:
            response = input().lower()
            return response in ['y', 'yes']
        except KeyboardInterrupt:
            return False 