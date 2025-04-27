from django.core.management.base import BaseCommand, CommandError
import os
import sys
import logging
from datetime import datetime
from django.db import connection
import yaml

from semantis_app.models import Judgment
from semantis_app.utils.metadata import MetadataParser, process_missing_metadata

class Command(BaseCommand):
    help = 'Stage 2: Fix metadata for judgments for all courts or specific court for a given year'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--court', type=str, help='Optional: Specific court code (e.g., ZACC). If not provided, all courts will be processed.')
    
    def setup_logging(self):
        """Setup logging for the command"""
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'stage2_metadata_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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
        
    def fix_metadata_for_court(self, court, year):
        """
        Specifically fix metadata for the specified court and year.
        Returns count of judgments updated.
        """
        try:
            # Find all judgments for this court and year
            judgments = Judgment.objects.filter(court=court, neutral_citation_year=year)
            initial_count = judgments.count()
            
            # If no judgments found, try to find by just court (might be missing year)
            if initial_count == 0:
                self.stdout.write(self.style.WARNING(f"[{court}] Warning: No judgments found with court={court} and year={year}. Trying just court."))
                judgments = Judgment.objects.filter(court=court)
                self.stdout.write(f"[{court}] Found {judgments.count()} judgments with just court filter.")
                
            # If still no judgments, try text search
            if judgments.count() == 0:
                self.stdout.write(self.style.WARNING(f"[{court}] Warning: No judgments found for court {court}. Trying text search."))
                judgments = Judgment.objects.filter(text_markdown__icontains=court)
                self.stdout.write(f"[{court}] Found {judgments.count()} judgments with text search.")
            
            # If still no judgments after all attempts
            if judgments.count() == 0:
                self.stdout.write(self.style.ERROR(f"[{court}] No judgments found to process for {court} {year}. Skipping."))
                return 0
            
            updated_count = 0
            
            for judgment in judgments:
                self.stdout.write(f"[{court}] Processing metadata for judgment: {judgment.id} - {judgment.title}")
                
                # Extract metadata from title and text
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
                        self.stdout.write(self.style.SUCCESS(f"[{court}] Updated fields for judgment {judgment.id}: {', '.join(fields_updated)}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"[{court}] Warning: No fields updated for judgment {judgment.id}"))
            
            return updated_count
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[{court}] Error fixing metadata: {str(e)}"))
            return 0
    
    def handle(self, *args, **options):
        logger = self.setup_logging()
        
        # Get parameters
        year = options['year']
        specific_court = options.get('court')
        
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
        total_updated = 0
        success_count = 0
        failure_count = 0
        
        for court in courts_to_process:
            self.stdout.write(self.style.SUCCESS(f"[{court}] STAGE 2: Fixing metadata for {court} {year}"))
            
            try:
                updated_count = self.fix_metadata_for_court(court, year)
                if updated_count > 0:
                    self.stdout.write(self.style.SUCCESS(f"[{court}] Successfully updated metadata for {updated_count} judgments"))
                    logger.info(f"[{court}] Updated metadata for {updated_count} judgments")
                    success_count += 1
                    total_updated += updated_count
                else:
                    self.stdout.write(self.style.WARNING(f"[{court}] No metadata updates needed for {court} {year}"))
                    logger.info(f"[{court}] No metadata updates needed")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{court}] Error fixing metadata: {str(e)}"))
                logger.error(f"[{court}] Error: {str(e)}")
                failure_count += 1
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(f"Stage 2 complete: Updated metadata for {total_updated} judgments across {success_count} courts, failed {failure_count} courts")) 