from django.core.management.base import BaseCommand, CommandError
import os
import sys
import logging
from datetime import datetime
from django.db import connection
import yaml
import subprocess
import atexit

from semantis_app.utils.scraping import scrape_court_year, ScrapingError

class Command(BaseCommand):
    help = 'Stage 1: Scrape judgments for all courts or specific court for a given year'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--court', type=str, help='Optional: Specific court code (e.g., ZACC). If not provided, all courts will be processed.')
        parser.add_argument('--retry-attempts', type=int, default=3, help='Number of retry attempts')
        parser.add_argument('--prevent-sleep', action='store_true', help='Prevent computer from sleeping during execution')
    
    def setup_logging(self):
        """Setup logging for the command"""
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'stage1_scrape_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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
    
    def handle(self, *args, **options):
        logger = self.setup_logging()
        
        # Get parameters
        year = options['year']
        specific_court = options.get('court')
        retry_attempts = options.get('retry_attempts', 3)
        prevent_sleep = options.get('prevent_sleep', False)
        
        # Start caffeinate process if requested
        caffeinate_process = None
        if prevent_sleep:
            self.stdout.write(self.style.SUCCESS("Starting sleep prevention..."))
            # -d prevents display sleep, -i prevents system idle sleep
            caffeinate_process = subprocess.Popen(["caffeinate", "-di"])
            
            # Make sure we clean up the caffeinate process when script exits
            def terminate_caffeinate():
                if caffeinate_process:
                    self.stdout.write(self.style.SUCCESS("Terminating sleep prevention..."))
                    caffeinate_process.terminate()
            
            atexit.register(terminate_caffeinate)
        
        try:
            # Check database connection
            if not self.check_database_connection():
                self.stdout.write(self.style.ERROR("Database connection failed. Aborting process."))
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
            success_count = 0
            failure_count = 0
            
            for court in courts_to_process:
                self.stdout.write(self.style.SUCCESS(f"[{court}] STAGE 1: Scraping judgments for {court} {year}"))
                
                # Try with retries
                for attempt in range(1, retry_attempts + 1):
                    try:
                        scrape_results = scrape_court_year(court, year)
                        self.stdout.write(self.style.SUCCESS(f"[{court}] Scraping complete: {scrape_results}"))
                        logger.info(f"[{court}] Scraping complete: {scrape_results}")
                        success_count += 1
                        break
                    except ScrapingError as e:
                        self.stdout.write(self.style.ERROR(f"[{court}] Scraping error (attempt {attempt}/{retry_attempts}): {str(e)}"))
                        logger.error(f"[{court}] Scraping error: {str(e)}")
                        if attempt == retry_attempts:
                            self.stdout.write(self.style.ERROR(f"[{court}] Failed after {retry_attempts} attempts"))
                            failure_count += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"[{court}] Unexpected error (attempt {attempt}/{retry_attempts}): {str(e)}"))
                        logger.error(f"[{court}] Unexpected error: {str(e)}")
                        if attempt == retry_attempts:
                            self.stdout.write(self.style.ERROR(f"[{court}] Failed after {retry_attempts} attempts"))
                            failure_count += 1
            
            # Final summary
            self.stdout.write(self.style.SUCCESS(f"Stage 1 complete: Successfully scraped {success_count} courts, failed {failure_count} courts"))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nProcess interrupted by user."))
        finally:
            # Clean up caffeinate process if it exists
            if caffeinate_process:
                self.stdout.write(self.style.SUCCESS("Terminating sleep prevention..."))
                caffeinate_process.terminate()
                atexit.unregister(terminate_caffeinate) 