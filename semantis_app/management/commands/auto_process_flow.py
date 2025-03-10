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
        """Setup logging for the command but don't use it directly - use print instead"""
        # Configure logging to file only (not used for console output)
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'auto_process_flow_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename)
            ]
        )
        
    def check_database_connection(self):
        """Test database connection before starting processing"""
        court = getattr(self, 'current_court', 'SYSTEM')
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                print(f"[{court}] Database connection successful")
                sys.stdout.flush()
            return True
        except Exception as e:
            print(f"[{court}] Database connection failed: {str(e)}")
            sys.stdout.flush()
            return False

    def load_and_verify_court_codes(self, court_code):
        """
        Ensure court codes are properly loaded, including from courts.yaml file in either location.
        Returns True if the specified court code is found.
        """
        court = getattr(self, 'current_court', court_code)
        
        # First check if MetadataParser has the code already
        court_codes = MetadataParser.get_court_codes()
        
        if court_code in court_codes:
            print(f"[{court}] Found court code {court_code} in configured courts")
            sys.stdout.flush()
            return True
            
        # If not, try to load from courts.yaml in semantis_app directory
        try:
            yaml_path = os.path.join('semantis_app', 'config', 'courts.yaml')
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                
                # Check if court code exists in the YAML data
                for court_info in data:
                    if court_info.get('code') == court_code:
                        print(f"[{court}] Found court code {court_code} in courts.yaml file")
                        sys.stdout.flush()
                        return True
                        
            # Also check semantis_app/courts.yaml as a fallback
            yaml_path = os.path.join('semantis_app', 'courts.yaml')
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = f.read()
                
                if court_code in data:
                    print(f"[{court}] Found court code {court_code} in courts.yaml file")
                    sys.stdout.flush()
                    return True
        except Exception as e:
            print(f"[{court}] Error checking courts.yaml file: {str(e)}")
            sys.stdout.flush()
            
        print(f"[{court}] Warning: Court code {court_code} not found in configured courts")
        sys.stdout.flush()
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
                print(f"[{court}] Warning: No judgments found with court={court} and year={year}. Trying just court.")
                sys.stdout.flush()
                judgments = Judgment.objects.filter(court=court)
                
            # If still no judgments, try text search
            if judgments.count() == 0:
                print(f"[{court}] Warning: No judgments found for court {court}. Trying text search.")
                sys.stdout.flush()
                judgments = Judgment.objects.filter(text_markdown__icontains=court)
            
            updated_count = 0
            
            for judgment in judgments:
                print(f"[{court}] Processing metadata for judgment: {judgment.id} - {judgment.title}")
                sys.stdout.flush()
                
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
                        print(f"[{court}] Updated fields for judgment {judgment.id}: {', '.join(fields_updated)}")
                        sys.stdout.flush()
                    else:
                        print(f"[{court}] Warning: No fields updated for judgment {judgment.id}")
                        sys.stdout.flush()
            
            return updated_count
                    
        except Exception as e:
            print(f"[{court}] Error fixing metadata: {str(e)}")
            sys.stdout.flush()
            return 0

    def process_judgments(self, court, year, retry_attempts=3):
        """
        Process all judgments for the given court and year through all stages
        without requiring confirmation.
        """
        self.current_court = court
        start_time = datetime.now()
        print(f"[{court}] Starting automated process flow for {court} {year}")
        sys.stdout.flush()
        
        try:
            # 1. Check database connection
            if not self.check_database_connection():
                print(f"[{court}] Database connection failed. Aborting process.")
                sys.stdout.flush()
                return False
                
            # 2. Verify the court code is valid
            is_valid = self.load_and_verify_court_codes(court)
            if not is_valid:
                print(f"[{court}] Warning: Court code {court} not found in configured courts. Continuing anyway.")
                sys.stdout.flush()
                
            # 3. Scrape judgments
            print(f"[{court}] STAGE 1: Scraping judgments for {court} {year}")
            sys.stdout.flush()
            scrape_results = scrape_court_year(court, year)
            print(f"[{court}] Scraping complete: {scrape_results}")
            sys.stdout.flush()
            
            # 4. Fix metadata extraction
            print(f"[{court}] STAGE 2: Fixing metadata")
            sys.stdout.flush()
            updated_count = self.fix_metadata_for_court(court, year)
            print(f"[{court}] Metadata fixed for {updated_count} judgments")
            sys.stdout.flush()
            
            # 5. Chunk judgments
            print(f"[{court}] STAGE 3: Chunking judgments")
            sys.stdout.flush()
            chunk_result = chunk_judgments()
            print(f"[{court}] Chunking complete: {chunk_result} judgments processed")
            sys.stdout.flush()
            
            # 6. Generate embeddings
            print(f"[{court}] STAGE 4: Generating embeddings")
            sys.stdout.flush()
            embed_result = generate_embeddings(batch_size=20)
            print(f"[{court}] Embedding complete: {embed_result} judgments processed")
            sys.stdout.flush()
            
            # 7. Generate short summaries
            print(f"[{court}] STAGE 5: Generating short summaries")
            sys.stdout.flush()
            summary_result = process_short_summaries(batch_size=20, target_court=court)
            print(f"[{court}] Short summaries complete: {summary_result} judgments processed")
            sys.stdout.flush()
            
            # 8. Calculate reportability scores
            print(f"[{court}] STAGE 6: Calculating reportability scores")
            sys.stdout.flush()
            reportability_result = process_reportability(batch_size=20, target_court=court)
            print(f"[{court}] Reportability scoring complete: {reportability_result} judgments processed")
            sys.stdout.flush()
            
            # 9. Generate long summaries for high-scoring judgments
            print(f"[{court}] STAGE 7: Generating long summaries")
            sys.stdout.flush()
            long_summary_result = summarize_judgments(batch_size=10, target_court=court)
            print(f"[{court}] Long summaries complete: {long_summary_result} judgments processed")
            sys.stdout.flush()
            
            # 10. Classify practice areas if available
            if PRACTICE_AREAS_AVAILABLE:
                print(f"[{court}] STAGE 8: Classifying practice areas")
                sys.stdout.flush()
                practice_area_result = classify_judgments(batch_size=20, target_court=court)
                print(f"[{court}] Practice area classification complete: {practice_area_result} judgments processed")
                sys.stdout.flush()
            else:
                print(f"[{court}] Warning: Practice areas classification not available - skipping")
                sys.stdout.flush()
            
            # Calculate statistics
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Generate success message
            print(f"[{court}] Automated process flow complete in {duration}")
            sys.stdout.flush()
            
            # Check for judgments
            final_count = Judgment.objects.filter(court=court, neutral_citation_year=year).count()
            if final_count == 0:
                print(f"[{court}] Warning: No judgments found for {court} {year} after processing")
                sys.stdout.flush()
                return False
                
            return True
            
        except Exception as e:
            import traceback
            print(f"[{court}] Error in automated process flow: {str(e)}")
            print(f"[{court}] {traceback.format_exc()}")
            sys.stdout.flush()
            return False

    def handle(self, *args, **options):
        """Main command execution."""
        court = options['court']
        year = options['year']
        retry_attempts = options['retry_attempts']
        
        # Set the current court for use in other methods
        self.current_court = court
        
        start_time = datetime.now()
        
        # Print colorful information about what we're doing
        print(f"[{court}] Starting automated process flow for {court} {year}")
        sys.stdout.flush()
        print(f"[{court}] Court: {court}")
        sys.stdout.flush()
        print(f"[{court}] Year: {year}")
        sys.stdout.flush()
        print(f"[{court}] Retry attempts: {retry_attempts}")
        sys.stdout.flush()
        
        self.setup_logging()
        
        # Check if the database connection is working correctly
        print(f"[{court}] Checking database connection...")
        sys.stdout.flush()
        
        db_working = self.check_database_connection()
        if db_working:
            print(f"[{court}] Database connection successful")
            sys.stdout.flush()
        else:
            print(f"[{court}] Error: Database connection failed")
            sys.stdout.flush()
            return
        
        # Verify the court code exists in our YAML file
        print(f"[{court}] Verifying court code: {court}")
        sys.stdout.flush()
        
        court_code_valid = self.load_and_verify_court_codes(court)
        if not court_code_valid:
            print(f"[{court}] Error: Invalid court code {court}")
            sys.stdout.flush()
            return
        else:
            print(f"[{court}] Court code {court} validated")
            sys.stdout.flush()
            
        # Handle the actual judgment processing
        print(f"[{court}] ==================================================")
        sys.stdout.flush()
        print(f"[{court}] PROCESSING {court} {year}")
        sys.stdout.flush()
        print(f"[{court}] ==================================================")
        sys.stdout.flush()
        
        success = self.process_judgments(court, year, retry_attempts)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        if success:
            print(f"[{court}] ==================================================")
            sys.stdout.flush()
            print(f"[{court}] COMPLETED: Successfully processed {court} {year}")
            sys.stdout.flush() 
            print(f"[{court}] Process duration: {duration}")
            sys.stdout.flush()
            print(f"[{court}] ==================================================")
            sys.stdout.flush()
            print(f"[{court}] PROCESS COMPLETE SUCCESS") 
            sys.stdout.flush()
        else:
            print(f"[{court}] ==================================================")
            sys.stdout.flush()
            print(f"[{court}] FAILED: Error processing {court} {year}")
            sys.stdout.flush()
            print(f"[{court}] Process duration: {duration}")
            sys.stdout.flush()
            print(f"[{court}] ==================================================")
            sys.stdout.flush()
            print(f"[{court}] PROCESS COMPLETE FAILURE")
            sys.stdout.flush() 