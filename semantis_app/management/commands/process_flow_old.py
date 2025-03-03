import os
import time
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from enum import Enum, auto
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

# Import utility functions from respective modules
from semantis_app.utils.scraping import scrape_court_year
from semantis_app.utils.chunking import process_pending_judgments as chunk_judgments
from semantis_app.utils.embedding import generate_embeddings
from semantis_app.utils.metadata import process_missing_metadata
from semantis_app.utils.short_summary import process_all_cases as process_short_summaries
from semantis_app.utils.reportability_score import process_cases as process_reportability
from semantis_app.utils.long_summary import summarize_judgments
from semantis_app.models import Judgment

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Stage(Enum):
    """Enum representing processing stages with clear, descriptive names."""
    SCRAPING = auto()
    METADATA = auto()
    CHUNKING = auto()
    EMBEDDING = auto()
    SHORT_SUMMARY = auto()
    REPORTABILITY = auto()
    LONG_SUMMARY = auto()

class ProcessingConfig:
    """Configuration class for processing parameters."""
    def __init__(
        self, 
        court: str, 
        year: int, 
        case_number: Optional[int] = None,
        batch_size: Optional[int] = None,
        force: bool = False
    ):
        self.court = court
        self.year = year
        self.case_number = case_number
        self.batch_size = batch_size or 50
        self.force = force

class StageProcessor:
    """Centralized processor for different stages of judgment processing."""
    
    @staticmethod
    def process_stage(stage: Stage, config: ProcessingConfig) -> Dict:
        """
        Process a single stage with comprehensive error handling and logging.
        
        Args:
            stage (Stage): The processing stage
            config (ProcessingConfig): Configuration parameters
        
        Returns:
            Dict: Processing statistics
        """
        stats = {
            'processed': 0,
            'errors': 0,
            'skipped': 0
        }
        
        try:
            logger.info(f"Processing stage: {stage.name}")
            
            if stage == Stage.SCRAPING:
                if config.case_number:
                    judgments = [StageProcessor._scrape_single_case(config)]
                else:
                    judgments = scrape_court_year(config.court, config.year)
                stats['processed'] = len(judgments)
                
            elif stage == Stage.METADATA:
                stats['processed'] = process_missing_metadata(batch_size=config.batch_size)
                
            elif stage == Stage.CHUNKING:
                stats['processed'] = chunk_judgments()
                
            elif stage == Stage.EMBEDDING:
                generate_embeddings(batch_size=config.batch_size)
                stats['processed'] = Judgment.objects.filter(chunks_embedded=True).count()
                
            elif stage == Stage.SHORT_SUMMARY:
                stats['processed'] = process_short_summaries(
                    batch_size=config.batch_size, 
                    force=config.force, 
                    target_court=config.court
                )
                
            elif stage == Stage.REPORTABILITY:
                stats['processed'] = process_reportability(
                    target_court=config.court, 
                    batch_size=config.batch_size
                )
                
            elif stage == Stage.LONG_SUMMARY:
                stats['processed'] = summarize_judgments(
                    target_court=config.court, 
                    batch_size=config.batch_size
                )
            
            return stats
        
        except Exception as e:
            logger.error(f"Error in {stage.name} stage: {str(e)}")
            stats['errors'] = 1
            raise
    
    @staticmethod
    def _scrape_single_case(config: ProcessingConfig):
        """Helper method to scrape a single case."""
        url = f"https://www.saflii.org/za/cases/{config.court}/{config.year}/{config.case_number}.html"
        logger.info(f"Scraping single case from: {url}")
        
        judgments = scrape_court_year(
            config.court, 
            config.year, 
            single_case_url=url
        )
        
        return judgments[0] if judgments else None

class Command(BaseCommand):
    """Django management command for processing legal judgments."""
    help = 'Process legal judgments through multiple stages'

    def add_arguments(self, parser):
        """Define command-line arguments."""
        parser.add_argument('--court', type=str, required=True, help='Court code')
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--case-number', type=int, help='Specific case number')
        parser.add_argument('--batch-size', type=int, help='Batch size for processing')
        parser.add_argument('--force', action='store_true', help='Force reprocessing')
        parser.add_argument('--start-stage', type=str, choices=[s.name for s in Stage], 
                            default=Stage.SCRAPING.name, help='Stage to start from')
        parser.add_argument('--end-stage', type=str, choices=[s.name for s in Stage], 
                            help='Stage to end at')

    def handle(self, *args, **options):
        """Main entry point for the command."""
        start_time = datetime.now()
        
        try:
            # Create processing configuration
            config = ProcessingConfig(
                court=options['court'],
                year=options['year'],
                case_number=options.get('case_number'),
                batch_size=options.get('batch_size'),
                force=options.get('force', False)
            )
            
            # Determine stages to process
            stages = list(Stage)
            start_index = stages.index(Stage[options['start_stage']])
            end_index = stages.index(Stage[options['end_stage']]) if options['end_stage'] else len(stages) - 1
            
            # Process stages
            total_stats = {
                'processed': 0,
                'errors': 0,
                'stages_completed': 0
            }
            
            for stage in stages[start_index:end_index+1]:
                stage_stats = StageProcessor.process_stage(stage, config)
                total_stats['processed'] += stage_stats['processed']
                total_stats['errors'] += stage_stats['errors']
                total_stats['stages_completed'] += 1
                
                # Optional delay between stages
                time.sleep(2)
            
            # Generate and log report
            self._log_report(total_stats, start_time)
            
        except Exception as e:
            logger.error(f"Processing failed: {str(e)}")
            raise CommandError(str(e))

    def _log_report(self, total_stats: Dict, start_time: datetime):
        """Generate and log a processing report."""
        end_time = datetime.now()
        duration = end_time - start_time
        
        report = [
            "\n" + "=" * 80,
            "PROCESS FLOW REPORT",
            "=" * 80,
            f"\nTotal Processing Time: {duration}",
            f"Total Items Processed: {total_stats['processed']}",
            f"Total Errors: {total_stats['errors']}",
            f"Stages Completed: {total_stats['stages_completed']}"
        ]
        
        logger.info("\n".join(report)) 