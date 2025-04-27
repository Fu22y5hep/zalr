from django.core.management.base import BaseCommand, CommandError
import os
import sys
import logging
from datetime import datetime
from django.db import connection
import yaml

from semantis_app.models import Judgment
from semantis_app.utils.reportability_score import process_cases

class Command(BaseCommand):
    help = 'Stage 6: Calculate reportability scores for judgments for all courts or specific court for a given year'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--court', type=str, help='Optional: Specific court code (e.g., ZACC). If not provided, all courts will be processed.')
        parser.add_argument('--batch-size', type=int, default=10, help='Number of judgments to process in one batch (default: 10)')
        parser.add_argument('--judgment-id', type=str, help='Process only this specific judgment ID (optional)')
        parser.add_argument('--force', action='store_true', help='Force recalculation of reportability scores for judgments that already have them')
    
    def setup_logging(self):
        """Setup logging for the command"""
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'stage6_reportability_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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
    
    def calculate_reportability_for_court_year(self, court, year, batch_size=10, force=False):
        """
        Calculate reportability scores for judgments from the specified court and year.
        Returns count of judgments processed.
        """
        try:
            # Get judgments for this court and year
            query = Judgment.objects.filter(court=court, neutral_citation_year=year)
            
            # If not force, only process judgments without reportability scores
            if not force:
                query = query.filter(reportability_score__isnull=True)
            
            judgment_count = query.count()
            
            if judgment_count == 0:
                self.stdout.write(self.style.WARNING(f"[{court}] No judgments found that need reportability scores for {court} {year}"))
                return 0
            
            self.stdout.write(self.style.SUCCESS(f"[{court}] Found {judgment_count} judgments that need reportability scores"))
            
            # Process judgments for reportability scores
            processed_judgments = []
            
            # Get judgment IDs for processing
            judgment_ids = list(query.values_list('id', flat=True))
            
            # Process in batches
            for i in range(0, len(judgment_ids), batch_size):
                batch = judgment_ids[i:i+batch_size]
                self.stdout.write(f"[{court}] Processing batch {i//batch_size + 1}/{(len(judgment_ids) + batch_size - 1)//batch_size}")
                
                try:
                    # Process this batch
                    batch_result = process_cases(judgment_ids=batch, force=force)
                    processed_judgments.extend(batch_result)
                    self.stdout.write(self.style.SUCCESS(f"[{court}] Successfully processed batch of {len(batch)} judgments"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"[{court}] Error processing batch: {str(e)}"))
            
            return len(processed_judgments)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[{court}] Error calculating reportability scores: {str(e)}"))
            return 0
    
    def handle(self, *args, **options):
        logger = self.setup_logging()
        
        # Get parameters
        year = options['year']
        specific_court = options.get('court')
        judgment_id = options.get('judgment_id')
        batch_size = options.get('batch-size', 10)
        force = options.get('force', False)
        
        # Check database connection
        if not self.check_database_connection():
            self.stdout.write(self.style.ERROR("Database connection failed. Aborting process."))
            return
        
        # Handle single judgment case
        if judgment_id:
            self.stdout.write(self.style.SUCCESS(f"Processing reportability score for single judgment: {judgment_id}"))
            try:
                # Process just this judgment
                result = process_cases(judgment_ids=[judgment_id], force=force)
                if result:
                    self.stdout.write(self.style.SUCCESS(f"Successfully calculated reportability score for judgment {judgment_id}"))
                else:
                    self.stdout.write(self.style.WARNING(f"No reportability score calculated for judgment {judgment_id}"))
                return
            except Exception as e:
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
        total_processed = 0
        success_count = 0
        failure_count = 0
        
        for court in courts_to_process:
            self.stdout.write(self.style.SUCCESS(f"[{court}] STAGE 6: Calculating reportability scores for {court} {year}"))
            
            try:
                processed_count = self.calculate_reportability_for_court_year(court, year, batch_size, force)
                if processed_count > 0:
                    self.stdout.write(self.style.SUCCESS(f"[{court}] Successfully calculated reportability scores for {processed_count} judgments"))
                    logger.info(f"[{court}] Calculated reportability scores for {processed_count} judgments")
                    success_count += 1
                    total_processed += processed_count
                else:
                    self.stdout.write(self.style.WARNING(f"[{court}] No judgments needed reportability scores for {court} {year}"))
                    logger.info(f"[{court}] No judgments needed reportability scores")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{court}] Error calculating reportability scores: {str(e)}"))
                logger.error(f"[{court}] Error: {str(e)}")
                failure_count += 1
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(f"Stage 6 complete: Calculated reportability scores for {total_processed} judgments across {success_count} courts, failed {failure_count} courts")) 