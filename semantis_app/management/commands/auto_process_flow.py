from django.core.management.base import BaseCommand, CommandError
import logging
import os
import time
import sys
from datetime import datetime
from typing import Optional, Dict, Tuple, List
from django.db import connection, transaction
from django.db.models import Q
import yaml

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

class Command(BaseCommand):
    help = 'Automated process flow for legal judgments (No confirmations needed)'

    def add_arguments(self, parser):
        parser.add_argument('--court', type=str, required=True, help='Court code (e.g., ZACC)')
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--retry-attempts', type=int, default=3, help='Number of retry attempts per stage')
        
    def setup_logging(self):
        # Configure logging with timestamp in filename
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'auto_process_flow_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_filename)
            ]
        )
        return logging.getLogger(__name__)

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

    def load_and_verify_court_codes(self, court_code):
        """
        Ensure court codes are properly loaded, including from courts.yaml file in either location.
        Returns True if the specified court code is found.
        """
        # First check if MetadataParser has the code already
        court_codes = MetadataParser.get_court_codes()
        
        if court_code in court_codes:
            self.logger.info(f"Found court code {court_code} in configured courts")
            return True
            
        # If not, try to load from courts.yaml in semantis_app directory
        try:
            yaml_path = os.path.join('semantis_app', 'courts.yaml')
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = f.read()
                
                if court_code in data:
                    self.logger.info(f"Found court code {court_code} in courts.yaml file")
                    return True
        except Exception as e:
            self.logger.warning(f"Error checking courts.yaml file: {str(e)}")
            
        self.logger.warning(f"Court code {court_code} not found in configured courts")
        return False

    def fix_metadata_for_court(self, court, year):
        """
        Specifically fix metadata for the specified court and year.
        Returns count of judgments updated.
        """
        try:
            # Find all judgments for this court and year
            judgments = Judgment.objects.filter(court=court, neutral_citation_year=year)
            
            # If no judgments found, try to find by just court (might be missing year)
            if judgments.count() == 0:
                self.logger.warning(f"No judgments found with court={court} and year={year}. Trying just court.")
                judgments = Judgment.objects.filter(court=court)
                
            # If still no judgments, try text search
            if judgments.count() == 0:
                self.logger.warning(f"No judgments found for court {court}. Trying text search.")
                judgments = Judgment.objects.filter(text_markdown__icontains=court)
            
            updated_count = 0
            
            for judgment in judgments:
                self.logger.info(f"Processing metadata for judgment: {judgment.id} - {judgment.title}")
                
                # Extract metadata from title
                if judgment.title:
                    parser = MetadataParser(judgment.text_markdown, judgment.title)
                    metadata = parser.extract_all()
                    
                    # Force court code if not extracted
                    if 'court' not in metadata or not metadata['court']:
                        metadata['court'] = court
                    
                    # Force year if not extracted
                    if 'neutral_citation_year' not in metadata or not metadata['neutral_citation_year']:
                        metadata['neutral_citation_year'] = year
                    
                    # Update the judgment
                    fields_updated = []
                    for key, value in metadata.items():
                        if hasattr(judgment, key) and value:
                            setattr(judgment, key, value)
                            fields_updated.append(key)
                    
                    if fields_updated:
                        judgment.save()
                        updated_count += 1
                        self.logger.info(f"Updated fields for judgment {judgment.id}: {', '.join(fields_updated)}")
                    else:
                        self.logger.warning(f"No fields updated for judgment {judgment.id}")
            
            return updated_count
                    
        except Exception as e:
            self.logger.error(f"Error fixing metadata: {str(e)}")
            return 0

    def process_judgments(self, court, year, retry_attempts=3):
        """
        Process all judgments for the given court and year through all stages
        without requiring confirmation.
        """
        start_time = datetime.now()
        self.logger.info(f"Starting automated process flow for {court} {year}")
        
        try:
            # 1. Check database connection
            if not self.check_database_connection():
                self.logger.error("Database connection failed. Aborting process.")
                return False
                
            # 2. Verify the court code is valid
            is_valid = self.load_and_verify_court_codes(court)
            if not is_valid:
                self.logger.warning(f"Court code {court} not found in configured courts. Continuing anyway.")
                
            # 3. Scrape judgments
            self.logger.info(f"STAGE 1: Scraping judgments for {court} {year}")
            scrape_results = scrape_court_year(court, year)
            self.logger.info(f"Scraping complete: {scrape_results}")
            
            # 4. Fix metadata extraction
            self.logger.info(f"STAGE 2: Fixing metadata")
            updated_count = self.fix_metadata_for_court(court, year)
            self.logger.info(f"Metadata fixed for {updated_count} judgments")
            
            # 5. Chunk judgments
            self.logger.info(f"STAGE 3: Chunking judgments")
            chunk_result = chunk_judgments()
            self.logger.info(f"Chunking complete: {chunk_result} judgments processed")
            
            # 6. Generate embeddings
            self.logger.info(f"STAGE 4: Generating embeddings")
            embed_result = generate_embeddings(batch_size=20)
            self.logger.info(f"Embedding complete: {embed_result} judgments processed")
            
            # 7. Generate short summaries
            self.logger.info(f"STAGE 5: Generating short summaries")
            summary_result = process_short_summaries(batch_size=20, target_court=court)
            self.logger.info(f"Short summaries complete: {summary_result} judgments processed")
            
            # 8. Calculate reportability scores
            self.logger.info(f"STAGE 6: Calculating reportability scores")
            reportability_result = process_reportability(batch_size=20, target_court=court)
            self.logger.info(f"Reportability scoring complete: {reportability_result} judgments processed")
            
            # 9. Generate long summaries for high-scoring judgments
            self.logger.info(f"STAGE 7: Generating long summaries")
            long_summary_result = summarize_judgments(batch_size=10, target_court=court)
            self.logger.info(f"Long summaries complete: {long_summary_result} judgments processed")
            
            # 10. Classify practice areas if available
            if PRACTICE_AREAS_AVAILABLE:
                self.logger.info(f"STAGE 8: Classifying practice areas")
                practice_area_result = classify_judgments(batch_size=20, target_court=court)
                self.logger.info(f"Practice area classification complete: {practice_area_result} judgments processed")
            else:
                self.logger.warning("Practice areas classification not available - skipping")
            
            # Calculate statistics
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Generate success message
            self.logger.info(f"Automated process flow complete in {duration}")
            
            # Check for judgments
            final_count = Judgment.objects.filter(court=court, neutral_citation_year=year).count()
            if final_count == 0:
                self.logger.warning(f"No judgments found for {court} {year} after processing")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error in automated process flow: {str(e)}", exc_info=True)
            return False

    def handle(self, *args, **options):
        self.logger = self.setup_logging()
        
        # Get command options
        court = options['court']
        year = options['year']
        retry_attempts = options.get('retry_attempts', 3)
        
        try:
            # Start the automated process
            self.stdout.write(self.style.SUCCESS(f"Starting automated process flow"))
            self.stdout.write(f"Processing court: {court}, year: {year}")
            
            success = self.process_judgments(court, year, retry_attempts)
            
            if success:
                self.stdout.write(self.style.SUCCESS(f"Automated process flow completed successfully"))
            else:
                self.stdout.write(self.style.ERROR(f"Automated process flow failed"))
                raise CommandError("Process flow failed")
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nProcess interrupted by user"))
            raise CommandError("Process interrupted by user") 