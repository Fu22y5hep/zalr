from django.core.management.base import BaseCommand, CommandError
import logging
import os
import time
from datetime import datetime
from typing import Optional, Dict, Tuple
from enum import Enum, auto

# Set tokenizers parallelism to false to avoid deadlocks
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from semantis_app.models import Judgment
from semantis_app.utils.scraping import scrape_court_year
from semantis_app.utils.chunking import process_pending_judgments as chunk_judgments
from semantis_app.utils.embedding import generate_embeddings
from semantis_app.utils.metadata import process_missing_metadata
from semantis_app.utils.short_summary import process_all_cases as process_short_summaries
from semantis_app.utils.reportability_score import process_cases as process_reportability
from semantis_app.utils.long_summary import summarize_judgments
from django.db.models import Q

class Stage(Enum):
    SCRAPING = auto()
    CHUNKING = auto()
    EMBEDDING = auto()
    METADATA = auto()
    SHORT_SUMMARY = auto()
    REPORTABILITY = auto()
    LONG_SUMMARY = auto()

class Command(BaseCommand):
    help = 'Process legal judgments through all stages (scraping, chunking, embedding, etc.)'

    def add_arguments(self, parser):
        parser.add_argument('--court', type=str, required=True, help='Court code (e.g., ZACC)')
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--case-number', type=int, help='Specific case number to process (e.g., 1 for [2025] ZACC 1)')
        parser.add_argument('--force', action='store_true', help='Force reprocessing of all stages')
        parser.add_argument('--start-stage', type=str, choices=[s.name for s in Stage], 
                          default=Stage.SCRAPING.name, help='Stage to start from')

    def setup_logging(self):
        # Configure logging with timestamp in filename
        log_filename = f'process_flow_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
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

    def check_stage_completion(self, stage: Stage, court: str, year: int, case_number: Optional[int] = None) -> Tuple[bool, int]:
        """
        Check if a stage has been completed for a court/year combination or specific case.
        Returns (is_complete, count) where count is the number of items processed.
        """
        try:
            # Get judgments for this court and year
            judgments = Judgment.objects.filter(court=court)
            if year:  # Some judgments might not have dates
                judgments = judgments.filter(judgment_date__year=year)
            if case_number:  # If processing a specific case
                judgments = judgments.filter(neutral_citation_number=case_number)
            
            total_count = judgments.count()
            if total_count == 0:
                return False, 0  # No judgments found
                
            if stage == Stage.SCRAPING:
                # If we have any judgments for this court/year/case, scraping is done
                return True, total_count
                
            elif stage == Stage.CHUNKING:
                processed = judgments.exclude(chunks__isnull=True).count()
                return processed == total_count, processed
                
            elif stage == Stage.EMBEDDING:
                processed = judgments.filter(chunks_embedded=True).count()
                return processed == total_count, processed
                
            elif stage == Stage.METADATA:
                processed = judgments.exclude(
                    Q(full_citation__isnull=True) |
                    Q(case_number__isnull=True) |
                    Q(judgment_date__isnull=True) |
                    Q(judges__isnull=True)
                ).count()
                return processed == total_count, processed
                
            elif stage == Stage.SHORT_SUMMARY:
                processed = judgments.exclude(short_summary__isnull=True).count()
                return processed == total_count, processed
                
            elif stage == Stage.REPORTABILITY:
                processed = judgments.exclude(reportability_score=0).count()
                return processed == total_count, processed
                
            elif stage == Stage.LONG_SUMMARY:
                # Long summaries are only for high-scoring judgments
                high_scoring = judgments.filter(reportability_score__gte=75).count()
                processed = judgments.exclude(long_summary__isnull=True).count()
                return processed == high_scoring, processed
                
        except Exception as e:
            self.logger.error(f"Error checking stage completion: {str(e)}")
            return False, 0

    def validate_stage(self, stage: Stage, court: str, year: int, case_number: Optional[int] = None) -> Tuple[bool, list]:
        """
        Validate that a stage has been properly completed for all judgments.
        Returns (is_valid, failed_judgments) where failed_judgments is a list of judgment IDs that need reprocessing.
        """
        try:
            # Get judgments for this court and year
            judgments = Judgment.objects.filter(court=court)
            if year:
                judgments = judgments.filter(judgment_date__year=year)
            if case_number:
                judgments = judgments.filter(neutral_citation_number=case_number)
            
            failed_judgments = []
            
            for judgment in judgments:
                if stage == Stage.SCRAPING:
                    # Verify judgment has basic required fields
                    if not all([judgment.text, judgment.url, judgment.court, judgment.judgment_date]):
                        failed_judgments.append(judgment.id)
                        
                elif stage == Stage.CHUNKING:
                    # Verify judgment has chunks
                    if not judgment.chunks or len(judgment.chunks) == 0:
                        failed_judgments.append(judgment.id)
                        
                elif stage == Stage.EMBEDDING:
                    # Verify judgment chunks are embedded
                    if not judgment.chunks_embedded:
                        failed_judgments.append(judgment.id)
                        
                elif stage == Stage.METADATA:
                    # Verify all metadata fields are present
                    if not all([
                        judgment.full_citation,
                        judgment.case_number,
                        judgment.judgment_date,
                        judgment.judges
                    ]):
                        failed_judgments.append(judgment.id)
                        
                elif stage == Stage.SHORT_SUMMARY:
                    # Verify short summary exists and is not empty
                    if not judgment.short_summary or len(judgment.short_summary.strip()) == 0:
                        failed_judgments.append(judgment.id)
                        
                elif stage == Stage.REPORTABILITY:
                    # Verify reportability score has been calculated
                    if judgment.reportability_score == 0:  # 0 indicates not processed
                        failed_judgments.append(judgment.id)
                        
                elif stage == Stage.LONG_SUMMARY:
                    # Only validate long summary for high-scoring judgments
                    if judgment.reportability_score >= 75:
                        if not judgment.long_summary or len(judgment.long_summary.strip()) == 0:
                            failed_judgments.append(judgment.id)
            
            return len(failed_judgments) == 0, failed_judgments
            
        except Exception as e:
            self.logger.error(f"Error validating stage {stage.name}: {str(e)}")
            return False, []

    def generate_report(self, court: str, year: int, total_stats: Dict, start_time: datetime, end_time: datetime) -> str:
        """Generate a detailed process flow report."""
        # Get completion status for all stages
        stage_status = []
        for stage in Stage:
            is_valid, failed_judgments = self.validate_stage(stage, court, year)
            status = "Complete" if is_valid else f"Incomplete ({len(failed_judgments)} failed)"
            stage_status.append(f"{self.get_stage_name(stage)}: {status}")

        report = [
            "\n" + "=" * 80,
            "PROCESS FLOW REPORT",
            "=" * 80,
            f"\nExecution Details:",
            f"Court: {court}",
            f"Year: {year}",
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
            f"Total Judgments: {Judgment.objects.count()}",
            f"Judgments with Chunks: {Judgment.objects.exclude(chunks__isnull=True).count()}",
            f"Judgments with Embeddings: {Judgment.objects.filter(chunks_embedded=True).count()}",
            f"Judgments with Short Summaries: {Judgment.objects.exclude(short_summary__isnull=True).count()}",
            f"Judgments with Long Summaries: {Judgment.objects.exclude(long_summary__isnull=True).count()}",
            f"High-Scoring Judgments (>=75): {Judgment.objects.filter(reportability_score__gte=75).count()}",
            "\nStage Details:",
        ]

        # Add stage-specific statistics
        for stage in Stage:
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

    def process_stage(self, stage: Stage, court: str, year: int, force: bool = False, case_number: Optional[int] = None) -> Dict:
        """Process a single stage and return statistics"""
        stats = {'processed': 0, 'errors': 0, 'skipped': 0, 'retries': 0}
        max_retries = 3  # Maximum number of retry attempts
        retry_delay = 5  # Seconds to wait between retries
        
        try:
            # Check if stage is already complete
            is_complete, completed_count = self.check_stage_completion(stage, court, year, case_number)
            
            if is_complete and not force:
                self.logger.info(f"Stage {self.get_stage_name(stage)} already completed for {court} {year}{f' case {case_number}' if case_number else ''}. Validating...")
                
                # Even if complete, validate the stage
                is_valid, failed_judgments = self.validate_stage(stage, court, year, case_number)
                if is_valid:
                    self.logger.info("Validation successful. All judgments properly processed.")
                    stats['skipped'] = completed_count
                    return stats
                else:
                    self.logger.warning(f"Found {len(failed_judgments)} judgments that need reprocessing")
                    force = True  # Force processing of failed judgments
            
            for attempt in range(max_retries):
                if attempt > 0:
                    self.logger.info(f"Retry attempt {attempt + 1} of {max_retries}")
                    time.sleep(retry_delay)
                    stats['retries'] += 1
                
                if stage == Stage.SCRAPING:
                    if case_number:
                        self.logger.info(f"Processing single case")
                        judgment = self.scrape_single_case(court, year, case_number)
                        stats['processed'] = 1 if judgment else 0
                    else:
                        judgments = scrape_court_year(court, year)
                        stats['processed'] = len(judgments) if judgments else 0
                    
                elif stage == Stage.CHUNKING:
                    stats['processed'] = chunk_judgments()
                    
                elif stage == Stage.EMBEDDING:
                    generate_embeddings()
                    stats['processed'] = Judgment.objects.filter(chunks_embedded=True).count()
                    
                elif stage == Stage.METADATA:
                    stats['processed'] = process_missing_metadata()
                    
                elif stage == Stage.SHORT_SUMMARY:
                    stats['processed'] = process_short_summaries(batch_size=20, delay=2.0, force=force, target_court=court)
                    
                elif stage == Stage.REPORTABILITY:
                    stats['processed'] = process_reportability(target_court=court)
                    
                elif stage == Stage.LONG_SUMMARY:
                    stats['processed'] = summarize_judgments(target_court=court)
                
                # Validate the results
                is_valid, failed_judgments = self.validate_stage(stage, court, year, case_number)
                if is_valid:
                    self.logger.info("Stage validation successful")
                    break
                elif attempt < max_retries - 1:  # Don't log on last attempt
                    self.logger.warning(f"Validation failed. {len(failed_judgments)} judgments need reprocessing. Retrying...")
                else:
                    self.logger.error(f"Stage validation failed after {max_retries} attempts. Failed judgments: {failed_judgments}")
                    stats['errors'] += len(failed_judgments)
                
        except Exception as e:
            self.logger.error(f"Error in {self.get_stage_name(stage)}: {str(e)}", exc_info=True)
            stats['errors'] += 1
            raise CommandError(f"Failed during {self.get_stage_name(stage)}: {str(e)}")
            
        return stats

    def scrape_single_case(self, court: str, year: int, case_number: int) -> Optional[Judgment]:
        """Scrape a single case from SAFLII."""
        try:
            url = f"https://www.saflii.org/za/cases/{court}/{year}/{case_number}.html"
            self.logger.info(f"Attempting to scrape case from: {url}")
            
            judgments = scrape_court_year(court, year, single_case_url=url)
            
            if judgments and len(judgments) > 0:
                # Get the judgment we just scraped
                judgment = Judgment.objects.filter(
                    court=court,
                    judgment_date__year=year,
                    neutral_citation_number=case_number
                ).first()
                return judgment
                
            return None
            
        except Exception as e:
            self.logger.error(f"Error scraping single case: {str(e)}")
            return None

    def process_court_year(self, court: str, year: int, start_stage: Stage = Stage.SCRAPING, force: bool = False, case_number: Optional[int] = None) -> bool:
        """Process all judgments for a specific court and year through all stages."""
        stages = list(Stage)
        start_index = stages.index(start_stage)
        start_time = datetime.now()
        
        total_stats = {
            'processed': 0,
            'errors': 0,
            'skipped': 0,
            'stages_completed': 0
        }
        
        try:
            # If processing a single case, verify it exists or try to scrape it
            if case_number:
                judgment = Judgment.objects.filter(
                    court=court,
                    judgment_date__year=year,
                    neutral_citation_number=case_number
                ).first()
                
                if not judgment:
                    self.logger.info(f"Case not found in database, attempting to scrape: {court} {year} {case_number}")
                    judgment = self.scrape_single_case(court, year, case_number)
                    
                if not judgment:
                    self.logger.error(f"Case not found and could not be scraped: {court} {year} {case_number}")
                    return False
                    
                self.logger.info(f"Processing single case: {judgment.full_citation or f'{court} {year} {case_number}'}")
            
            for stage in stages[start_index:]:
                stage_name = self.get_stage_name(stage)
                self.stdout.write(self.style.MIGRATE_HEADING(f"Stage {stage.value}: {stage_name}"))
                
                stage_start_time = time.time()
                stats = self.process_stage(stage, court, year, force, case_number)
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
                total_stats['stages_completed'] += 1
                
                # Log stage completion
                self.logger.info(f"Completed {stage_name} in {duration:.2f} seconds")
                self.logger.info(f"Stage statistics: {stats}")
                
                # Add a delay between stages to prevent rate limiting
                if stage != stages[-1]:  # Don't delay after the last stage
                    time.sleep(2)
            
            # Generate and log the final report
            end_time = datetime.now()
            report = self.generate_report(court, year, total_stats, start_time, end_time)
            self.logger.info(report)
            
            # Also save report to a separate file
            report_filename = f'process_flow_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            with open(report_filename, 'w') as f:
                f.write(report)
            
            return True
            
        except CommandError as e:
            self.logger.error(str(e))
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error in process flow: {str(e)}", exc_info=True)
            return False
        finally:
            # Log final statistics
            self.stdout.write("\nFinal Statistics:")
            self.stdout.write(f"Total items processed: {total_stats['processed']}")
            self.stdout.write(f"Total errors: {total_stats['errors']}")
            self.stdout.write(f"Total skipped: {total_stats['skipped']}")
            self.stdout.write(f"Stages completed: {total_stats['stages_completed']}/{len(stages[start_index:])}")

    def handle(self, *args, **options):
        self.logger = self.setup_logging()
        start_time = datetime.now()
        
        self.stdout.write(self.style.SUCCESS(f"Starting process flow at {start_time}"))
        self.stdout.write(f"Processing court: {options['court']}, year: {options['year']}")
        if options['case_number']:
            self.stdout.write(f"Processing specific case: {options['case_number']}")
        self.stdout.write(f"Force mode: {'enabled' if options['force'] else 'disabled'}")
        self.stdout.write(f"Starting from stage: {options['start_stage']}")

        try:
            start_stage = Stage[options['start_stage']]
            success = self.process_court_year(
                options['court'], 
                options['year'], 
                start_stage, 
                options['force'], 
                options['case_number']
            )
            
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