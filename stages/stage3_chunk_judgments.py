from django.core.management.base import BaseCommand, CommandError
import os
import sys
import logging
from datetime import datetime
from django.db import connection
import yaml

from semantis_app.models import Judgment
from semantis_app.utils.chunking import process_pending_judgments, chunk_judgment

class Command(BaseCommand):
    help = 'Stage 3: Chunk judgments for all courts or specific court for a given year'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--court', type=str, help='Optional: Specific court code (e.g., ZACC). If not provided, all courts will be processed.')
        parser.add_argument('--batch-size', type=int, default=10, help='Number of judgments to process in one batch (default: 10)')
        parser.add_argument('--judgment-id', type=str, help='Process only this specific judgment ID (optional)')
    
    def setup_logging(self):
        """Setup logging for the command"""
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'stage3_chunking_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename)
            ]
        )
        return logging.getLogger(__name__)
    
    def check_database_connection(self):
        """Verify database connection is working"""
        try:
            connection.ensure_connection()
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Database connection error: {str(e)}"))
            return False
    
    def load_court_codes(self):
        """Load all valid court codes from configuration"""
        court_codes = []
        try:
            with open('court_config.yaml', 'r') as file:
                court_config = yaml.safe_load(file)
                for court in court_config.get('courts', []):
                    court_codes.append(court.get('code'))
            return court_codes
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Warning: Could not load court codes: {str(e)}"))
            # Fallback to a default list of common court codes
            return ['ZACC', 'ZASCA', 'ZAGPPHC', 'ZAWCHC', 'ZAKZDHC']

    def validate_court_code(self, court):
        """Validate if the provided court code is valid"""
        court_codes = self.load_court_codes()
        if court in court_codes:
            return True
        return False
    
    def chunk_judgments_for_court_year(self, court, year, batch_size=10):
        """
        Specifically chunk judgments for the specified court and year.
        Returns count of judgments chunked.
        """
        try:
            # Find all judgments for this court and year that need chunking
            # (Assumes that judgments that need chunking have no associated chunks)
            from django.db.models import Count
            judgments = Judgment.objects.filter(court=court, neutral_citation_year=year)\
                .annotate(chunk_count=Count('chunks'))\
                .filter(chunk_count=0)
            
            initial_count = judgments.count()
            
            if initial_count == 0:
                self.stdout.write(self.style.WARNING(f"[{court}] No judgments found that need chunking for {court} {year}"))
                return 0
            
            self.stdout.write(self.style.SUCCESS(f"[{court}] Found {initial_count} judgments that need chunking"))
            
            # Process each judgment
            chunked_count = 0
            for judgment in judgments:
                try:
                    self.stdout.write(f"[{court}] Chunking judgment: {judgment.id} - {judgment.title}")
                    chunks = chunk_judgment(judgment.id)
                    if chunks and len(chunks) > 0:
                        chunked_count += 1
                        self.stdout.write(self.style.SUCCESS(f"[{court}] Successfully created {len(chunks)} chunks for judgment {judgment.id}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"[{court}] No chunks created for judgment {judgment.id}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"[{court}] Error chunking judgment {judgment.id}: {str(e)}"))
            
            return chunked_count
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[{court}] Error during chunking: {str(e)}"))
            return 0
    
    def handle(self, *args, **options):
        logger = self.setup_logging()
        
        # Get parameters
        year = options['year']
        specific_court = options.get('court')
        judgment_id = options.get('judgment_id')
        batch_size = options.get('batch_size', 10)
        
        # Check database connection
        if not self.check_database_connection():
            self.stdout.write(self.style.ERROR("Database connection failed. Aborting process."))
            return
        
        # Handle single judgment case
        if judgment_id:
            self.stdout.write(self.style.SUCCESS(f"Processing single judgment: {judgment_id}"))
            try:
                chunks = chunk_judgment(judgment_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully created {len(chunks)} chunks for judgment {judgment_id}"))
                return
            except ValueError as e:
                self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
                return
        
        # Get list of courts to process
        courts_to_process = []
        if specific_court:
            if self.validate_court_code(specific_court):
                courts_to_process = [specific_court]
                self.stdout.write(self.style.SUCCESS(f"Processing single court: {specific_court}"))
            else:
                self.stdout.write(self.style.WARNING(f"Warning: Court code {specific_court} not found in configured courts."))
                proceed = input(f"Continue with unknown court code {specific_court}? (y/n): ")
                if proceed.lower() == 'y':
                    courts_to_process = [specific_court]
                else:
                    self.stdout.write(self.style.ERROR("Aborted."))
                    return
        else:
            courts_to_process = self.load_court_codes()
            self.stdout.write(self.style.SUCCESS(f"Processing all {len(courts_to_process)} courts for year {year}"))
        
        # Process each court
        total_chunked = 0
        success_count = 0
        failure_count = 0
        
        for court in courts_to_process:
            self.stdout.write(self.style.SUCCESS(f"[{court}] STAGE 3: Chunking judgments for {court} {year}"))
            
            try:
                chunked_count = self.chunk_judgments_for_court_year(court, year, batch_size)
                if chunked_count > 0:
                    self.stdout.write(self.style.SUCCESS(f"[{court}] Successfully chunked {chunked_count} judgments"))
                    logger.info(f"[{court}] Chunked {chunked_count} judgments")
                    success_count += 1
                    total_chunked += chunked_count
                else:
                    self.stdout.write(self.style.WARNING(f"[{court}] No judgments needed chunking for {court} {year}"))
                    logger.info(f"[{court}] No judgments needed chunking")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{court}] Error chunking judgments: {str(e)}"))
                logger.error(f"[{court}] Error: {str(e)}")
                failure_count += 1
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(f"Stage 3 complete: Chunked {total_chunked} judgments across {success_count} courts, failed {failure_count} courts")) 