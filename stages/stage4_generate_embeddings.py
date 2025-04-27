from django.core.management.base import BaseCommand, CommandError
import os
import sys
import logging
from datetime import datetime
from django.db import connection
import yaml
import time
import numpy as np

from semantis_app.models import Judgment
from semantis_app.utils.embedding import EmbeddingGenerator

class Command(BaseCommand):
    help = 'Stage 4: Generate embeddings for judgment chunks for all courts or specific court for a given year'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True, help='Year to process')
        parser.add_argument('--court', type=str, help='Optional: Specific court code (e.g., ZACC). If not provided, all courts will be processed.')
        parser.add_argument('--batch-size', type=int, default=20, help='Number of chunks to process in one batch (default: 20)')
        parser.add_argument('--judgment-id', type=str, help='Process only chunks from this specific judgment ID (optional)')
        parser.add_argument('--force', action='store_true', help='Force regeneration of embeddings for chunks that already have them')
    
    def setup_logging(self):
        """Setup logging for the command"""
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f'stage4_embeddings_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename),
                logging.StreamHandler(sys.stdout)
            ]
        )
        return logging.getLogger(__name__)
    
    def check_database_connection(self):
        """Check if database connection is working"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Database connection error: {str(e)}"))
            return False
    
    def load_court_codes(self):
        """Load court codes from configuration file"""
        try:
            with open('court_config.yaml', 'r') as file:
                court_config = yaml.safe_load(file)
                court_codes = []
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
    
    def generate_embeddings_for_court_year(self, court, year, batch_size=20, force=False):
        """
        Generate embeddings for chunks of judgments from the specified court and year.
        Returns count of judgments processed.
        """
        try:
            # Get judgments for this court and year
            judgments = Judgment.objects.filter(court=court, neutral_citation_year=year)
            
            if not judgments.exists():
                self.stdout.write(self.style.WARNING(f"[{court}] No judgments found for {court} {year}"))
                return 0
                
            # Count judgments that need embedding
            if force:
                # Process all judgments regardless of embedding status
                pending_judgments = judgments
            else:
                # Only process judgments that don't have embeddings yet
                pending_judgments = judgments.filter(chunks_embedded=False)
            
            pending_judgments_count = pending_judgments.count()
            
            if pending_judgments_count == 0:
                self.stdout.write(self.style.WARNING(f"[{court}] No judgments found that need chunk embeddings for {court} {year}"))
                return 0
            
            self.stdout.write(self.style.SUCCESS(f"[{court}] Found {pending_judgments_count} judgments that need chunk embeddings"))
            
            # Create embedding generator and process these judgments
            generator = EmbeddingGenerator()
            generator.batch_size = batch_size
            
            processed_count = 0
            for judgment in pending_judgments:
                try:
                    if not judgment.chunks:
                        self.stdout.write(self.style.WARNING(f"[{court}] Judgment {judgment.id} has no chunks to process"))
                        continue
                        
                    # Get all chunks for this judgment
                    chunks = [chunk['content'] for chunk in judgment.chunks]
                    self.stdout.write(self.style.SUCCESS(f"[{court}] Processing judgment {judgment.id} with {len(chunks)} chunks"))
                    
                    # Process chunks in batches
                    embeddings = []
                    for i in range(0, len(chunks), generator.batch_size):
                        batch = chunks[i:i + generator.batch_size]
                        try:
                            # Get embeddings for the batch
                            response = generator.client.embed(batch, model=generator.model)
                            # Extract embeddings from response.embeddings list
                            batch_embeddings = [embedding for embedding in response.embeddings]
                            embeddings.extend(batch_embeddings)
                            self.stdout.write(self.style.SUCCESS(f"[{court}] Processed batch {i//generator.batch_size + 1} of {(len(chunks) + generator.batch_size - 1)//generator.batch_size}"))
                            time.sleep(generator.sleep_time)  # Be nice to the API
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"[{court}] Error processing batch for judgment {judgment.id}: {str(e)}"))
                            continue
                    
                    if embeddings:
                        # Calculate average embedding for the judgment
                        avg_embedding = np.mean(embeddings, axis=0)
                        
                        # Save the embedding
                        judgment.vector_embedding = avg_embedding
                        judgment.chunks_embedded = True
                        judgment.save()
                        
                        processed_count += 1
                        self.stdout.write(self.style.SUCCESS(f"[{court}] Successfully processed judgment {judgment.id} ({processed_count}/{pending_judgments_count})"))
                    else:
                        self.stdout.write(self.style.WARNING(f"[{court}] No embeddings generated for judgment {judgment.id}"))
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"[{court}] Error processing judgment {judgment.id}: {str(e)}"))
                    continue
            
            return processed_count
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[{court}] Error generating embeddings: {str(e)}"))
            return 0
    
    def generate_embeddings_for_judgment(self, judgment_id, batch_size=20, force=False):
        """Generate embeddings for chunks of a specific judgment"""
        try:
            # Get the specific judgment
            try:
                judgment = Judgment.objects.get(id=judgment_id)
            except Judgment.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Judgment with ID {judgment_id} not found"))
                return 0
            
            # Check if it needs processing
            if not force and judgment.chunks_embedded:
                self.stdout.write(self.style.WARNING(f"Judgment {judgment_id} already has embedded chunks. Use --force to reprocess."))
                return 0
            
            # Process the judgment
            self.stdout.write(self.style.SUCCESS(f"Processing judgment: {judgment.title}"))
            
            if not judgment.chunks:
                self.stdout.write(self.style.ERROR(f"Judgment {judgment_id} has no chunks to process"))
                return 0
            
            # Use the embedding generator
            generator = EmbeddingGenerator()
            generator.batch_size = batch_size
            
            # Process only this judgment
            try:
                chunks = [chunk['content'] for chunk in judgment.chunks]
                self.stdout.write(self.style.SUCCESS(f"Processing {len(chunks)} chunks for judgment {judgment_id}"))
                
                # Process chunks in batches
                embeddings = []
                for i in range(0, len(chunks), generator.batch_size):
                    batch = chunks[i:i + generator.batch_size]
                    try:
                        # Get embeddings for the batch
                        response = generator.client.embed(batch, model=generator.model)
                        # Extract embeddings from response.embeddings list
                        batch_embeddings = [embedding for embedding in response.embeddings]
                        embeddings.extend(batch_embeddings)
                        self.stdout.write(self.style.SUCCESS(f"Processed batch {i//generator.batch_size + 1} of {(len(chunks) + generator.batch_size - 1)//generator.batch_size}"))
                        time.sleep(generator.sleep_time)  # Be nice to the API
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Error processing batch for judgment {judgment_id}: {str(e)}"))
                        continue
                
                if embeddings:
                    # Calculate average embedding for the judgment
                    avg_embedding = np.mean(embeddings, axis=0)
                    
                    # Save the embedding
                    judgment.vector_embedding = avg_embedding
                    judgment.chunks_embedded = True
                    judgment.save()
                    
                    self.stdout.write(self.style.SUCCESS(f"Successfully processed judgment {judgment_id}"))
                    return 1
                else:
                    self.stdout.write(self.style.ERROR(f"No embeddings were generated for judgment {judgment_id}"))
                    return 0
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing judgment {judgment_id}: {str(e)}"))
                return 0
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error in generate_embeddings_for_judgment: {str(e)}"))
            return 0
    
    def handle(self, *args, **options):
        logger = self.setup_logging()
        
        # Get parameters
        year = options['year']
        specific_court = options.get('court')
        batch_size = options.get('batch-size', 20)
        judgment_id = options.get('judgment_id')
        force = options.get('force', False)
        
        # Check database connection
        if not self.check_database_connection():
            self.stdout.write(self.style.ERROR("Database connection failed. Aborting process."))
            return
        
        # Process a specific judgment if requested
        if judgment_id:
            self.stdout.write(self.style.SUCCESS(f"Processing single judgment: {judgment_id}"))
            success_count = self.generate_embeddings_for_judgment(judgment_id, batch_size, force)
            self.stdout.write(self.style.SUCCESS(f"Stage 4 complete for judgment {judgment_id}: {'Success' if success_count > 0 else 'Failed'}"))
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
            self.stdout.write(self.style.SUCCESS(f"[{court}] STAGE 4: Generating embeddings for {court} {year}"))
            
            result = self.generate_embeddings_for_court_year(court, year, batch_size, force)
            
            if result > 0:
                self.stdout.write(self.style.SUCCESS(f"[{court}] Successfully generated embeddings for {result} judgments"))
                success_count += 1
            else:
                self.stdout.write(self.style.WARNING(f"[{court}] No embeddings generated (no judgments to process)"))
                failure_count += 1
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(f"Stage 4 complete: Successfully processed {success_count} courts, skipped {failure_count} courts")) 