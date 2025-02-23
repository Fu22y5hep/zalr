from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from semantis_app.utils.reportability_score import process_cases, analyze_text, save_reportability_score, save_scoring_sections
from semantis_app.models import Judgment
import sys
import time

class Command(BaseCommand):
    help = 'Process reportability scores for judgments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of judgments to process in each batch (default: 10)'
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
            '--court',
            type=str,
            choices=['ZACC', 'ZASCA', 'ZAGPJHC', 'ZAGPPHC', 'ZAWCHC', 'ZAKZDHC', 'ZAECG'],
            help='Process judgments from specific court (e.g., ZACC)'
        )
        parser.add_argument(
            '--year',
            type=int,
            help='Process judgments from specific year (e.g., 2024)'
        )
        parser.add_argument(
            '--start-number',
            type=int,
            help='Start from this neutral citation number'
        )
        parser.add_argument(
            '--end-number',
            type=int,
            help='End at this neutral citation number (inclusive)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress for each judgment'
        )

    def get_judgments_to_process(self, options) -> list[Judgment]:
        """Get judgments based on filtering criteria."""
        query = Q(reportability_score=0)  # Unscored judgments

        # Apply filters
        court = options.get('court')
        year = options.get('year')
        start_number = options.get('start_number')
        end_number = options.get('end_number')

        if court:
            query &= Q(court=court)
        if year:
            query &= Q(neutral_citation_year=year)
        if start_number is not None:
            query &= Q(neutral_citation_number__gte=start_number)
        if end_number is not None:
            query &= Q(neutral_citation_number__lte=end_number)

        # Order by citation number for consistent processing
        judgments = Judgment.objects.filter(query).order_by(
            'neutral_citation_year', 'neutral_citation_number'
        )

        return judgments

    def handle(self, *args, **options):
        batch_size = options.get('batch_size')
        dry_run = options.get('dry_run')
        continue_on_error = options.get('continue_on_error')
        verbose = options.get('verbose')

        try:
            # Get judgments to process
            judgments = self.get_judgments_to_process(options)
            total_judgments = judgments.count()
            
            if total_judgments == 0:
                self.stdout.write("No judgments found that need processing.")
                return

            # Show filtering criteria
            self.stdout.write("\nProcessing with filters:")
            if options.get('court'):
                self.stdout.write(f"Court: {options['court']}")
            if options.get('year'):
                self.stdout.write(f"Year: {options['year']}")
            if options.get('start_number'):
                self.stdout.write(f"Starting from citation number: {options['start_number']}")
            if options.get('end_number'):
                self.stdout.write(f"Ending at citation number: {options['end_number']}")
            
            self.stdout.write(f"\nFound {total_judgments} judgments to process")
            
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"DRY RUN: Would process reportability scores for {total_judgments} judgments"
                ))
                # Show what would be processed
                for judgment in judgments[:5]:
                    self.stdout.write(
                        f"Would process: [{judgment.neutral_citation_year}] "
                        f"{judgment.court} {judgment.neutral_citation_number}"
                    )
                if total_judgments > 5:
                    self.stdout.write(f"... and {total_judgments - 5} more")
                return

            # Start processing
            start_time = time.time()
            total_processed = 0
            batch_number = 1
            
            while True:
                batch_start = (batch_number - 1) * batch_size
                batch_end = batch_start + batch_size
                batch_judgments = judgments[batch_start:batch_end]
                
                if not batch_judgments:
                    break

                self.stdout.write(f"\nProcessing batch {batch_number}...")
                
                with transaction.atomic():
                    processed = 0
                    for judgment in batch_judgments:
                        try:
                            if verbose:
                                self.stdout.write(
                                    f"Processing [{judgment.neutral_citation_year}] "
                                    f"{judgment.court} {judgment.neutral_citation_number}"
                                )
                            
                            # Process the judgment using reportability_score functions
                            score, explanation = analyze_text(judgment.text_markdown)
                            if score is not None:
                                save_reportability_score(judgment.id, score, explanation)
                                save_scoring_sections(judgment.id, explanation)
                                processed += 1
                                if verbose:
                                    self.stdout.write(
                                        f"  Score: {score}"
                                    )
                            else:
                                self.stdout.write(self.style.WARNING(
                                    f"Could not generate score for judgment {judgment.id}"
                                ))
                                
                        except Exception as e:
                            if continue_on_error:
                                self.stdout.write(self.style.WARNING(
                                    f"Error processing judgment {judgment.id}: {str(e)}"
                                ))
                            else:
                                raise
                    
                    total_processed += processed
                
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
                
                # Ask for continuation after each batch
                if not self.confirm_continue():
                    break
            
            # Final summary
            self.stdout.write(self.style.SUCCESS(
                f"\nCompleted processing {total_processed} judgments\n"
                f"Total time: {time.time() - start_time:.2f} seconds"
            ))

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nProcessing interrupted by user"))
            sys.exit(1)
        except Exception as e:
            if not continue_on_error:
                raise CommandError(f"Error processing judgments: {str(e)}")
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