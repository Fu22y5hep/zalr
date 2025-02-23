import argparse
import logging
import sys
import os
import django
import time
from datetime import datetime
from typing import Optional, Dict
from enum import Enum, auto

# Add project root to Python path and setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalr_backend.settings')
django.setup()

from semantis_app.models import Judgment
from semantis_app.utils.scraping import scrape_court_year
from semantis_app.utils.chunking import process_pending_judgments as chunk_judgments
from semantis_app.utils.embedding import generate_embeddings
from semantis_app.utils.metadata import process_missing_metadata
from semantis_app.utils.short_summary import process_all_cases as process_short_summaries
from semantis_app.utils.reportability_score import process_cases as process_reportability
from semantis_app.utils.long_summary import summarize_judgments

class Stage(Enum):
    SCRAPING = auto()
    CHUNKING = auto()
    EMBEDDING = auto()
    METADATA = auto()
    SHORT_SUMMARY = auto()
    REPORTABILITY = auto()
    LONG_SUMMARY = auto()

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
logger = logging.getLogger(__name__)

class ProcessingError(Exception):
    """Custom exception for processing errors"""
    pass

def log_stage(stage: str):
    """Log a processing stage with a clear visual separator."""
    separator = "=" * 80
    logger.info(f"\n{separator}\n{stage}\n{separator}")

def get_stage_name(stage: Stage) -> str:
    """Convert stage enum to display name"""
    return stage.name.replace('_', ' ').title()

def process_stage(stage: Stage, court: str, year: int, force: bool = False) -> Dict:
    """Process a single stage and return statistics"""
    stats = {'processed': 0, 'errors': 0, 'skipped': 0}
    
    try:
        if stage == Stage.SCRAPING:
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
            process_short_summaries(force=force)
            stats['processed'] = Judgment.objects.exclude(short_summary__isnull=True).count()
            
        elif stage == Stage.REPORTABILITY:
            stats['processed'] = process_reportability(target_court=court)
            
        elif stage == Stage.LONG_SUMMARY:
            summarize_judgments(target_court=court)
            stats['processed'] = Judgment.objects.exclude(long_summary__isnull=True).count()
            
    except Exception as e:
        logger.error(f"Error in {get_stage_name(stage)}: {str(e)}", exc_info=True)
        stats['errors'] += 1
        raise ProcessingError(f"Failed during {get_stage_name(stage)}: {str(e)}")
        
    return stats

def process_court_year(court: str, year: int, start_stage: Stage = Stage.SCRAPING, force: bool = False) -> bool:
    """Process all judgments for a specific court and year through all stages."""
    stages = list(Stage)
    start_index = stages.index(start_stage)
    
    total_stats = {
        'processed': 0,
        'errors': 0,
        'skipped': 0,
        'stages_completed': 0
    }
    
    try:
        for stage in stages[start_index:]:
            stage_name = get_stage_name(stage)
            log_stage(f"Stage {stage.value}: {stage_name}")
            
            start_time = time.time()
            stats = process_stage(stage, court, year, force)
            duration = time.time() - start_time
            
            # Update total statistics
            total_stats['processed'] += stats['processed']
            total_stats['errors'] += stats['errors']
            total_stats['skipped'] += stats['skipped']
            total_stats['stages_completed'] += 1
            
            # Log stage completion
            logger.info(f"Completed {stage_name} in {duration:.2f} seconds")
            logger.info(f"Stage statistics: {stats}")
            
            # Add a delay between stages to prevent rate limiting
            if stage != stages[-1]:  # Don't delay after the last stage
                time.sleep(2)
        
        return True
        
    except ProcessingError as e:
        logger.error(str(e))
        return False
    except Exception as e:
        logger.error(f"Unexpected error in process flow: {str(e)}", exc_info=True)
        return False
    finally:
        # Log final statistics
        logger.info("\nFinal Statistics:")
        logger.info(f"Total items processed: {total_stats['processed']}")
        logger.info(f"Total errors: {total_stats['errors']}")
        logger.info(f"Total skipped: {total_stats['skipped']}")
        logger.info(f"Stages completed: {total_stats['stages_completed']}/{len(stages[start_index:])}")

def main():
    parser = argparse.ArgumentParser(description='Process legal judgments through all stages')
    parser.add_argument('--court', type=str, required=True, help='Court code (e.g., ZACC)')
    parser.add_argument('--year', type=int, required=True, help='Year to process')
    parser.add_argument('--force', action='store_true', help='Force reprocessing of all stages')
    parser.add_argument('--start-stage', type=str, choices=[s.name for s in Stage], 
                      default=Stage.SCRAPING.name, help='Stage to start from')
    args = parser.parse_args()

    start_time = datetime.now()
    logger.info(f"Starting process flow at {start_time}")
    logger.info(f"Processing court: {args.court}, year: {args.year}")
    logger.info(f"Force mode: {'enabled' if args.force else 'disabled'}")
    logger.info(f"Starting from stage: {args.start_stage}")

    try:
        start_stage = Stage[args.start_stage]
        success = process_court_year(args.court, args.year, start_stage, args.force)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        if success:
            logger.info(f"Process flow completed successfully in {duration}")
        else:
            logger.error(f"Process flow failed after {duration}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.warning("\nProcess interrupted by user")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(3)

if __name__ == "__main__":
    main() 