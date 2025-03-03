from django.core.management.base import BaseCommand, CommandError
import logging
import os
import time
import sys
from datetime import datetime
from typing import Optional, Dict, Tuple, List
from enum import Enum, auto
from django.db import connection, transaction
from django.db.models import Q

# Set tokenizers parallelism to false to avoid deadlocks
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from semantis_app.models import Judgment
from semantis_app.utils.scraping import scrape_court_year, ScrapingError
from semantis_app.utils.chunking import process_pending_judgments as chunk_judgments
from semantis_app.utils.chunking import chunk_judgment as chunk_single_judgment
from semantis_app.utils.embedding import generate_embeddings
from semantis_app.utils.metadata import process_missing_metadata, MetadataParser
from semantis_app.utils.short_summary import process_all_cases as process_short_summaries
from semantis_app.utils.reportability_score import process_cases as process_reportability
from semantis_app.utils.long_summary import summarize_judgments
try:
    from semantis_app.utils.practice_areas import classify_judgments
    PRACTICE_AREAS_AVAILABLE = True
except ImportError:
    PRACTICE_AREAS_AVAILABLE = False

class Stage(Enum):
    SCRAPING = auto()
    CHUNKING = auto()
    EMBEDDING = auto()
    SHORT_SUMMARY = auto()
    REPORTABILITY = auto()
    LONG_SUMMARY = auto()
    CLASSIFY_PRACTICE_AREAS = auto()  # New stage

class Command(BaseCommand):
    help = 'Process legal judgments through all stages (scraping, chunking, embedding, etc.)'

    def add_arguments(self, parser):
        parser.add_argument('--court', type=str, required=True, help='Court code (e.g., ZACC)')
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--case-number', type=int, help='Specific case number to process (e.g., 1 for [2025] ZACC 1)')
        parser.add_argument('--force', action='store_true', help='Force reprocessing of all stages')
        parser.add_argument('--start-stage', type=str, choices=[s.name for s in Stage], 
                          default=Stage.SCRAPING.name, help='Stage to start from')
        parser.add_argument('--skip-confirmation', action='store_true', help='Skip confirmation prompts')
        parser.add_argument('--retry-attempts', type=int, default=3, help='Number of retry attempts per stage')
        parser.add_argument('--force-continue', action='store_true', 
                          help='Continue to next stages even if current stage fails validation')
        
    def setup_logging(self):
        # Configure logging with timestamp in filename
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'process_flow_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_filename)
            ]
        )
        return logging.getLogger(__name__)

    def get_stage_name(self, stage: Stage) -> str:
        """Convert stage enum to display name"""
        return stage.name.replace('_', ' ').title()

    def check_database_connection(self):
        """Test database connection before starting processing"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                self.logger.info("Database connection successful")
            return True
        except Exception as e:
            self.logger.error(f"Database connection failed: {str(e)}")
            return False

    def check_stage_completion(self, stage: Stage, court: str, year: int, case_number: Optional[int] = None) -> Tuple[bool, int]:
        """
        Check if a stage has been completed for a court/year combination or specific case.
        Returns (is_complete, count) where count is the number of items processed.
        """
        try:
            # Build base query for judgments
            base_query = Q(court=court)
            if year:
                base_query &= Q(neutral_citation_year=year)
            if case_number:
                base_query &= Q(neutral_citation_number=case_number)
            
            judgments = Judgment.objects.filter(base_query)
            
            total_count = judgments.count()
            if total_count == 0:
                self.logger.warning(f"No judgments found for {court}/{year}/{case_number if case_number else 'all'}")
                return False, 0
            
            # Check completion based on stage
            if stage == Stage.SCRAPING:
                # Scraping is complete if we have judgments
                if case_number:
                    # For a single case, check if text_markdown exists
                    processed = judgments.exclude(text_markdown__isnull=True).exclude(text_markdown='').count()
                else:
                    processed = total_count
                return processed > 0, processed
            
            elif stage == Stage.CHUNKING:
                processed = judgments.exclude(chunks__isnull=True).count()
                return processed == total_count, processed
            
            elif stage == Stage.EMBEDDING:
                processed = judgments.filter(chunks_embedded=True).count()
                return processed == total_count, processed
            
            elif stage == Stage.SHORT_SUMMARY:
                processed = judgments.exclude(short_summary__isnull=True).exclude(short_summary='').count()
                return processed == total_count, processed
            
            elif stage == Stage.REPORTABILITY:
                processed = judgments.exclude(reportability_score=0).count()
                return processed == total_count, processed
            
            elif stage == Stage.LONG_SUMMARY:
                # Long summaries are only for high-scoring judgments
                high_scoring = judgments.filter(reportability_score__gte=75).count()
                if high_scoring == 0:
                    return True, 0  # No high-scoring judgments to process
                processed = judgments.filter(reportability_score__gte=75).exclude(long_summary__isnull=True).exclude(long_summary='').count()
                return processed == high_scoring, processed
                
            elif stage == Stage.CLASSIFY_PRACTICE_AREAS:
                # Check if practice areas have been assigned
                if not PRACTICE_AREAS_AVAILABLE:
                    return True, 0  # Skip if feature not available
                processed = judgments.exclude(practice_areas__isnull=True).exclude(practice_areas="").count()
                return processed == total_count, processed
            
        except Exception as e:
            self.logger.error(f"Error checking stage completion: {str(e)}")
            return False, 0

    def get_judgments_for_stage(self, stage: Stage, court: str, year: int, case_number: Optional[int] = None) -> List[Judgment]:
        """Get the judgments that need to be processed for a specific stage"""
        base_query = Q(court=court)
        if year:
            base_query &= Q(neutral_citation_year=year)
        if case_number:
            base_query &= Q(neutral_citation_number=case_number)
        
        # Add stage-specific filters
        if stage == Stage.CHUNKING:
            base_query &= Q(chunks__isnull=True)
        elif stage == Stage.EMBEDDING:
            base_query &= Q(chunks__isnull=False, chunks_embedded=False)
        elif stage == Stage.SHORT_SUMMARY:
            base_query &= Q(short_summary__isnull=True)
        elif stage == Stage.REPORTABILITY:
            base_query &= Q(reportability_score=0)
        elif stage == Stage.LONG_SUMMARY:
            base_query &= Q(reportability_score__gte=75, long_summary__isnull=True)
        elif stage == Stage.CLASSIFY_PRACTICE_AREAS and PRACTICE_AREAS_AVAILABLE:
            base_query &= Q(practice_areas__isnull=True)
        
        return Judgment.objects.filter(base_query)

    def validate_stage(self, stage: Stage, court: str, year: int, case_number: Optional[int] = None) -> Tuple[bool, List]:
        """
        Validate that a stage has been properly completed for all judgments.
        Returns (is_valid, failed_judgments) where failed_judgments is a list of judgment IDs that need reprocessing.
        """
        try:
            # Build base query for judgments
            base_query = Q(court=court)
            if year:
                base_query &= Q(neutral_citation_year=year)
            if case_number:
                base_query &= Q(neutral_citation_number=case_number)
            
            judgments = Judgment.objects.filter(base_query)
            failed_ids = []
            
            for judgment in judgments:
                # Validation logic specific to each stage
                if stage == Stage.SCRAPING:
                    if not judgment.text_markdown or len(judgment.text_markdown.strip()) == 0:
                        failed_ids.append(judgment.id)
                
                elif stage == Stage.CHUNKING:
                    if not judgment.chunks or len(judgment.chunks) == 0:
                        failed_ids.append(judgment.id)
                
                elif stage == Stage.EMBEDDING:
                    # Fixed check for embedded vector - properly handles NumPy arrays
                    if not judgment.chunks_embedded or judgment.vector_embedding is None:
                        failed_ids.append(judgment.id)
                
                elif stage == Stage.SHORT_SUMMARY:
                    if not judgment.short_summary or len(judgment.short_summary.strip()) == 0:
                        failed_ids.append(judgment.id)
                
                elif stage == Stage.REPORTABILITY:
                    if judgment.reportability_score == 0:
                        failed_ids.append(judgment.id)
                
                elif stage == Stage.LONG_SUMMARY:
                    if judgment.reportability_score >= 75 and (not judgment.long_summary or len(judgment.long_summary.strip()) == 0):
                        failed_ids.append(judgment.id)
                
                elif stage == Stage.CLASSIFY_PRACTICE_AREAS and PRACTICE_AREAS_AVAILABLE:
                    if not judgment.practice_areas or len(judgment.practice_areas.strip()) == 0:
                        failed_ids.append(judgment.id)
                        
            return len(failed_ids) == 0, failed_ids
            
        except Exception as e:
            self.logger.error(f"Error validating stage {stage.name}: {str(e)}")
            return False, []

    def generate_report(self, court: str, year: int, case_number: Optional[int] = None, 
                        total_stats: Dict = None, start_time: datetime = None, end_time: datetime = None) -> str:
        """Generate a detailed process flow report."""
        if not total_stats:
            total_stats = {'processed': 0, 'errors': 0, 'skipped': 0, 'stages_completed': 0}
        
        if not start_time:
            start_time = datetime.now()
        if not end_time:
            end_time = datetime.now()
            
        # Get completion status for all stages
        stage_status = []
        for stage in Stage:
            # Skip practice areas if not available
            if stage == Stage.CLASSIFY_PRACTICE_AREAS and not PRACTICE_AREAS_AVAILABLE:
                continue
                
            try:
                is_valid, failed_judgments = self.validate_stage(stage, court, year, case_number)
                status = "Complete" if is_valid else f"Incomplete ({len(failed_judgments)} failed)"
                stage_status.append(f"{self.get_stage_name(stage)}: {status}")
            except Exception as e:
                stage_status.append(f"{self.get_stage_name(stage)}: Error validating ({str(e)})")
            
        # Build query to count judgments
        base_query = Q(court=court)
        if year:
            base_query &= Q(neutral_citation_year=year)
        if case_number:
            base_query &= Q(neutral_citation_number=case_number)

        report = [
            "\n" + "=" * 80,
            "PROCESS FLOW REPORT",
            "=" * 80,
            f"\nExecution Details:",
            f"Court: {court}",
            f"Year: {year}",
            f"Case Number: {case_number if case_number else 'All'}",
            f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration: {end_time - start_time}",
            "\nStage Status:",
            *[f"  {status}" for status in stage_status],
            "\nProcessing Statistics:",
            f"Total Items Processed: {total_stats['processed']}",
            f"Total Errors: {total_stats['errors']}",
            f"Total Skipped: {total_stats['skipped']}",
            f"Total Retries: {total_stats.get('retries', 0)}",
            f"Stages Completed: {total_stats['stages_completed']}",
            "\nCurrent Database State:",
            f"Total Judgments: {Judgment.objects.filter(base_query).count()}",
            f"Judgments with Chunks: {Judgment.objects.filter(base_query).exclude(chunks__isnull=True).count()}",
            f"Judgments with Embeddings: {Judgment.objects.filter(base_query).filter(chunks_embedded=True).count()}",
            f"Judgments with Full Metadata: {Judgment.objects.filter(base_query).exclude(Q(full_citation__isnull=True) | Q(case_number__isnull=True) | Q(judgment_date__isnull=True) | Q(judges__isnull=True)).count()}",
            f"Judgments with Short Summaries: {Judgment.objects.filter(base_query).exclude(short_summary__isnull=True).count()}",
            f"Judgments with Reportability Scores: {Judgment.objects.filter(base_query).exclude(reportability_score=0).count()}",
            f"Judgments with Long Summaries: {Judgment.objects.filter(base_query).exclude(long_summary__isnull=True).count()}",
            f"High-Scoring Judgments (>=75): {Judgment.objects.filter(base_query).filter(reportability_score__gte=75).count()}",
        ]

        # Add practice areas count if available
        if PRACTICE_AREAS_AVAILABLE:
            report.append(f"Judgments with Practice Areas: {Judgment.objects.filter(base_query).exclude(practice_areas__isnull=True).exclude(practice_areas='').count()}")

        report.append("\nStage Details:")

        # Add stage-specific statistics
        for stage in Stage:
            if stage == Stage.CLASSIFY_PRACTICE_AREAS and not PRACTICE_AREAS_AVAILABLE:
                continue
                
            stage_stats = total_stats.get(f'stage_{stage.name.lower()}', {})
            if stage_stats:
                report.extend([
                    f"\n{self.get_stage_name(stage)}:",
                    f"  Processed: {stage_stats.get('processed', 0)}",
                    f"  Errors: {stage_stats.get('errors', 0)}",
                    f"  Skipped: {stage_stats.get('skipped', 0)}",
                    f"  Duration: {stage_stats.get('duration', 'N/A')}"
                ])

        report.append("\n" + "=" * 80)
        return "\n".join(report)

    def scrape_single_case(self, court: str, year: int, case_number: int) -> Optional[Judgment]:
        """Scrape a single case from SAFLII and ensure it's in the database."""
        try:
            # First check if judgment already exists
            judgment = Judgment.objects.filter(
                court=court,
                neutral_citation_year=year,
                neutral_citation_number=case_number
            ).first()
            
            if judgment:
                self.logger.info(f"Found existing judgment: {judgment.id}")
                return judgment
                
            # Construct URL for this case
            url = f"https://www.saflii.org/za/cases/{court}/{year}/{case_number}.html"
            self.logger.info(f"Attempting to scrape case from: {url}")
            
            # Use the single_case_url parameter to scrape just this specific case
            judgments = scrape_court_year(court, year, single_case_url=url)
            
            if judgments and len(judgments) > 0:
                # Get the judgment we just scraped (should be the only one)
                judgment = judgments[0]
                
                # Set neutral citation fields
                if not judgment.neutral_citation_year:
                    judgment.neutral_citation_year = year
                if not judgment.neutral_citation_number:
                    judgment.neutral_citation_number = case_number
                if not judgment.court:
                    judgment.court = court
                
                judgment.save()
                self.logger.info(f"Successfully scraped judgment: {judgment.id}")
                return judgment
            
            self.logger.error(f"Failed to scrape judgment: {court} {year} {case_number}")
            return None
            
        except ScrapingError as e:
            self.logger.error(f"Scraping error: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in scrape_single_case: {str(e)}")
            return None

    def process_stage(self, stage: Stage, court: str, year: int, force: bool = False, 
                     case_number: Optional[int] = None, retry_attempts: int = 3) -> Dict:
        """Process a single stage and return statistics"""
        stats = {'processed': 0, 'errors': 0, 'skipped': 0, 'retries': 0}
        retry_delay = 5  # Seconds to wait between retries
        
        # Skip practice areas stage if not available
        if stage == Stage.CLASSIFY_PRACTICE_AREAS and not PRACTICE_AREAS_AVAILABLE:
            self.logger.info("Practice areas classification not available - skipping stage")
            stats['skipped'] = 1
            return stats
        
        try:
            # Check if stage is already complete (unless force is True)
            if not force:
                is_complete, completed_count = self.check_stage_completion(stage, court, year, case_number)
                if is_complete:
                    self.logger.info(f"Stage {self.get_stage_name(stage)} already completed for {court} {year}{f' case {case_number}' if case_number else ''}. Validating...")
                    # Even if complete, validate the stage
                    try:
                        is_valid, failed_judgment_ids = self.validate_stage(stage, court, year, case_number)
                        if is_valid:
                            self.logger.info("Validation successful. All judgments properly processed.")
                            stats['skipped'] = completed_count
                            return stats
                        else:
                            self.logger.warning(f"Found {len(failed_judgment_ids)} judgments that need reprocessing")
                            force = True  # Force processing of failed judgments
                    except Exception as e:
                        self.logger.error(f"Error validating completed stage: {str(e)}")
                        force = True  # Force processing since validation failed
            
            # Process specific stage
            for attempt in range(retry_attempts):
                if attempt > 0:
                    self.logger.info(f"Retry attempt {attempt + 1} of {retry_attempts}")
                    time.sleep(retry_delay)
                    stats['retries'] += 1
                
                # Stage-specific processing
                if stage == Stage.SCRAPING:
                    if case_number:
                        self.logger.info(f"Processing single case: {court} {year} {case_number}")
                        judgment = self.scrape_single_case(court, year, case_number)
                        stats['processed'] = 1 if judgment else 0
                    else:
                        judgments = scrape_court_year(court, year)
                        stats['processed'] = len(judgments) if judgments else 0
                
                elif stage == Stage.CHUNKING:
                    if case_number:
                        # Get the specific judgment
                        judgment = Judgment.objects.filter(
                            court=court,
                            neutral_citation_year=year,
                            neutral_citation_number=case_number
                        ).first()
                        
                        if judgment:
                            chunks = chunk_single_judgment(str(judgment.id))
                            stats['processed'] = 1 if chunks else 0
                        else:
                            self.logger.error(f"Judgment not found: {court} {year} {case_number}")
                            stats['errors'] += 1
                            return stats
                    else:
                        stats['processed'] = chunk_judgments()
                
                elif stage == Stage.EMBEDDING:
                    generate_embeddings()
                    # Count processed judgments
                    judgment_query = Q(court=court, chunks_embedded=True)
                    if year:
                        judgment_query &= Q(neutral_citation_year=year)
                    if case_number:
                        judgment_query &= Q(neutral_citation_number=case_number)
                    stats['processed'] = Judgment.objects.filter(judgment_query).count()
                
                elif stage == Stage.SHORT_SUMMARY:
                    stats['processed'] = process_short_summaries(batch_size=20, delay=2.0, force=force, target_court=court)
                
                elif stage == Stage.REPORTABILITY:
                    stats['processed'] = process_reportability(target_court=court)
                
                elif stage == Stage.LONG_SUMMARY:
                    stats['processed'] = summarize_judgments(target_court=court)
                    
                elif stage == Stage.CLASSIFY_PRACTICE_AREAS and PRACTICE_AREAS_AVAILABLE:
                    # Call practice area classification function
                    if case_number:
                        # Get the specific judgment
                        judgment = Judgment.objects.filter(
                            court=court,
                            neutral_citation_year=year,
                            neutral_citation_number=case_number
                        ).first()
                        
                        if judgment:
                            # Process practice areas for this specific judgment
                            processed = classify_judgments(target_court=court, judgment_id=str(judgment.id))
                            stats['processed'] = processed
                        else:
                            self.logger.error(f"Judgment not found: {court} {year} {case_number}")
                            stats['errors'] += 1
                            return stats
                    else:
                        stats['processed'] = classify_judgments(target_court=court)
                
                # Validate the results
                try:
                    is_valid, failed_judgment_ids = self.validate_stage(stage, court, year, case_number)
                    if is_valid:
                        self.logger.info(f"Stage {self.get_stage_name(stage)} validation successful")
                        break
                    elif attempt < retry_attempts - 1:  # Don't log on last attempt
                        self.logger.warning(f"Validation failed. {len(failed_judgment_ids)} judgments need reprocessing. Retrying...")
                    else:
                        self.logger.error(f"Stage validation failed after {retry_attempts} attempts. Failed judgments: {failed_judgment_ids}")
                        stats['errors'] = len(failed_judgment_ids)
                except Exception as e:
                    self.logger.error(f"Error validating stage {stage.name}: {str(e)}")
                    if attempt < retry_attempts - 1:
                        self.logger.warning(f"Will retry due to validation error: {str(e)}")
                    else:
                        self.logger.error(f"Failed to validate stage after {retry_attempts} attempts due to error: {str(e)}")
                        stats['errors'] += 1
                
        except Exception as e:
            self.logger.error(f"Error in {self.get_stage_name(stage)}: {str(e)}", exc_info=True)
            stats['errors'] += 1
            
        return stats

    def process_court_year(self, court: str, year: int, start_stage: Stage = Stage.SCRAPING, 
                           force: bool = False, case_number: Optional[int] = None, 
                           skip_confirmation: bool = False, retry_attempts: int = 3,
                           force_continue: bool = False) -> bool:
        """Process all judgments for a specific court and year through all stages."""
        stages = list(Stage)
        
        # Filter out practice areas stage if not available
        if not PRACTICE_AREAS_AVAILABLE and Stage.CLASSIFY_PRACTICE_AREAS in stages:
            stages.remove(Stage.CLASSIFY_PRACTICE_AREAS)
            
        start_index = stages.index(start_stage)
        start_time = datetime.now()
        
        total_stats = {
            'processed': 0,
            'errors': 0,
            'skipped': 0,
            'retries': 0,
            'stages_completed': 0
        }
        
        try:
            # Check database connection
            if not self.check_database_connection():
                self.logger.error("Database connection failed. Aborting process.")
                return False
                
            # If processing a single case and starting from scraping, try to get/scrape it first
            if case_number and start_stage == Stage.SCRAPING:
                judgment = self.scrape_single_case(court, year, case_number)
                if not judgment:
                    self.logger.error(f"Failed to scrape or find judgment: {court} {year} {case_number}")
                    return False
                self.logger.info(f"Processing single case: {judgment.full_citation or f'{court} {year} {case_number}'}")
            
            # Process each stage
            for i, stage in enumerate(stages[start_index:], 1):
                stage_name = self.get_stage_name(stage)
                self.stdout.write(self.style.MIGRATE_HEADING(
                    f"Stage {i}/{len(stages[start_index:])}: {stage_name}"
                ))
                
                # Check dependencies before processing stage
                if stage != Stage.SCRAPING and not force_continue:
                    prev_stage = stages[stages.index(stage) - 1]
                    is_complete, _ = self.check_stage_completion(prev_stage, court, year, case_number)
                    if not is_complete and not force:
                        self.logger.error(f"Dependency stage {self.get_stage_name(prev_stage)} is not complete. Cannot proceed with {stage_name}.")
                        self.logger.info("Use --force-continue to override this check.")
                        if not skip_confirmation:
                            if not self.confirm_continue():
                                break
                
                stage_start_time = time.time()
                stats = self.process_stage(stage, court, year, force, case_number, retry_attempts)
                duration = time.time() - stage_start_time
                
                # Store stage-specific statistics
                total_stats[f'stage_{stage.name.lower()}'] = {
                    'processed': stats['processed'],
                    'errors': stats['errors'],
                    'skipped': stats['skipped'],
                    'duration': f"{duration:.2f} seconds"
                }
                
                # Update total statistics
                total_stats['processed'] += stats['processed']
                total_stats['errors'] += stats['errors']
                total_stats['skipped'] += stats['skipped']
                total_stats['retries'] += stats.get('retries', 0)
                
                # Check if stage completed successfully
                try:
                    is_valid, failed_judgment_ids = self.validate_stage(stage, court, year, case_number)
                    if is_valid:
                        total_stats['stages_completed'] += 1
                        self.logger.info(f"Completed {stage_name} successfully in {duration:.2f} seconds")
                    else:
                        self.logger.warning(f"Stage {stage_name} completed with errors. {len(failed_judgment_ids)} judgments failed validation.")
                except Exception as e:
                    self.logger.error(f"Error validating stage {stage.name}: {str(e)}")
                    if force_continue:
                        self.logger.warning(f"Continuing despite validation error due to --force-continue")
                    elif not skip_confirmation:
                        if not self.confirm_continue():
                            break
                
                self.logger.info(f"Stage statistics: {stats}")
                
                # Ask for confirmation before proceeding to next stage
                if not skip_confirmation and i < len(stages[start_index:]):
                    if not self.confirm_continue():
                        self.logger.info("Process stopped by user after stage: " + stage_name)
                        break
                
                # Add a delay between stages to prevent rate limiting
                if i < len(stages[start_index:]):  # Don't delay after the last stage
                    time.sleep(2)
            
            # Generate and log the final report
            end_time = datetime.now()
            report = self.generate_report(court, year, case_number, total_stats, start_time, end_time)
            self.logger.info(report)
            
            # Also save report to a separate file
            report_dir = 'reports'
            os.makedirs(report_dir, exist_ok=True)
            report_filename = os.path.join(report_dir, f'process_flow_report_{court}_{year}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
            with open(report_filename, 'w') as f:
                f.write(report)
            
            # Consider process successful if we processed more than we skipped,
            # even if there were some errors
            processed_something = total_stats['processed'] > 0
            return processed_something
            
        except Exception as e:
            self.logger.error(f"Unexpected error in process flow: {str(e)}", exc_info=True)
            return False
        finally:
            # Log final statistics
            self.stdout.write("\nFinal Statistics:")
            self.stdout.write(f"Total items processed: {total_stats['processed']}")
            self.stdout.write(f"Total errors: {total_stats['errors']}")
            self.stdout.write(f"Total skipped: {total_stats['skipped']}")
            self.stdout.write(f"Total retries: {total_stats['retries']}")
            self.stdout.write(f"Stages completed: {total_stats['stages_completed']}/{len(stages[start_index:])}")

    def confirm_continue(self) -> bool:
        """Ask user if they want to continue processing"""
        self.stdout.write("\nContinue processing next stage? [y/N] ")
        try:
            response = input().lower()
            return response in ['y', 'yes']
        except KeyboardInterrupt:
            return False

    def handle(self, *args, **options):
        self.logger = self.setup_logging()
        start_time = datetime.now()
        
        # Get command options
        court = options['court']
        year = options['year']
        case_number = options.get('case_number')
        force = options.get('force', False)
        force_continue = options.get('force_continue', False)
        start_stage_name = options.get('start_stage', Stage.SCRAPING.name)
        skip_confirmation = options.get('skip_confirmation', False)
        retry_attempts = options.get('retry_attempts', 3)
        
        # Log start message
        self.stdout.write(self.style.SUCCESS(f"Starting process flow at {start_time}"))
        self.stdout.write(f"Processing court: {court}, year: {year}")
        if case_number:
            self.stdout.write(f"Processing specific case: {case_number}")
        self.stdout.write(f"Force mode: {'enabled' if force else 'disabled'}")
        self.stdout.write(f"Force continue: {'enabled' if force_continue else 'disabled'}")
        self.stdout.write(f"Starting from stage: {start_stage_name}")
        self.stdout.write(f"Skip confirmation: {'enabled' if skip_confirmation else 'disabled'}")
        self.stdout.write(f"Retry attempts: {retry_attempts}")
        if not PRACTICE_AREAS_AVAILABLE:
            self.stdout.write(f"Practice areas classification: not available")

        try:
            # Convert start stage name to enum
            start_stage = Stage[start_stage_name]
            
            # Process court/year/case
            success = self.process_court_year(
                court=court, 
                year=year, 
                start_stage=start_stage, 
                force=force, 
                case_number=case_number,
                skip_confirmation=skip_confirmation,
                retry_attempts=retry_attempts,
                force_continue=force_continue
            )
            
            # Log completion message
            end_time = datetime.now()
            duration = end_time - start_time
            
            if success:
                self.stdout.write(self.style.SUCCESS(f"Process flow completed successfully in {duration}"))
            else:
                self.stdout.write(self.style.ERROR(f"Process flow failed after {duration}"))
                raise CommandError("Process flow failed")
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nProcess interrupted by user"))
            raise CommandError("Process interrupted by user")