import os
import numpy as np
from typing import List, Dict, Any
import voyageai
from dotenv import load_dotenv
from django.db import transaction
from semantis_app.models import Judgment
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

class EmbeddingGenerator:
    """
    Handles the generation of embeddings for judgment chunks using voyage-law-2.
    """
    
    def __init__(self):
        """Initialize the Voyage AI client and set up configuration."""
        self.client = voyageai.Client()
        self.model = "voyage-law-2"
        self.batch_size = 10  # Number of chunks to process in one batch
        self.sleep_time = 1  # Time to sleep between batches to avoid rate limits
    
    def process_pending_judgments(self, batch_size: int = None) -> int:
        """
        Process all judgments that have chunks but haven't been embedded yet.
        
        Args:
            batch_size: Optional override for batch size
            
        Returns:
            int: Number of judgments processed
        """
        if batch_size:
            self.batch_size = batch_size
            
        processed_count = 0
        
        # Get judgments that have chunks but aren't embedded yet
        pending_judgments = Judgment.objects.filter(chunks__isnull=False, chunks_embedded=False)
        total_judgments = pending_judgments.count()
        logger.info(f"Found {total_judgments} judgments to process")
        
        # Process in batches
        for judgment in pending_judgments:
            try:
                if not judgment.chunks:  # Skip if no chunks (shouldn't happen due to filter)
                    continue
                    
                # Get all chunks for this judgment
                chunks = [chunk['content'] for chunk in judgment.chunks]
                logger.info(f"Processing judgment {judgment.id} with {len(chunks)} chunks")
                
                # Process chunks in batches
                embeddings = []
                for i in range(0, len(chunks), self.batch_size):
                    batch = chunks[i:i + self.batch_size]
                    try:
                        # Get embeddings for the batch
                        response = self.client.embed(batch, model=self.model)
                        # Extract embeddings from response.embeddings list
                        batch_embeddings = [embedding for embedding in response.embeddings]
                        embeddings.extend(batch_embeddings)
                        logger.info(f"Processed batch {i//self.batch_size + 1} of {(len(chunks) + self.batch_size - 1)//self.batch_size}")
                        time.sleep(self.sleep_time)  # Be nice to the API
                    except Exception as e:
                        logger.error(f"Error processing batch for judgment {judgment.id}: {str(e)}")
                        # Log more details about the response
                        logger.error(f"Response type: {type(response)}")
                        logger.error(f"Response attributes: {dir(response)}")
                        if hasattr(response, 'embeddings'):
                            logger.error(f"Embeddings type: {type(response.embeddings)}")
                            logger.error(f"First embedding: {response.embeddings[0] if response.embeddings else None}")
                        continue
                
                if embeddings:
                    # Calculate average embedding for the judgment
                    avg_embedding = np.mean(embeddings, axis=0)
                    
                    # Save the embedding
                    with transaction.atomic():
                        judgment.vector_embedding = avg_embedding
                        judgment.chunks_embedded = True
                        judgment.save()
                    
                    processed_count += 1
                    logger.info(f"Successfully processed judgment {judgment.id} ({processed_count}/{total_judgments})")
                else:
                    logger.warning(f"No embeddings generated for judgment {judgment.id}")
                
            except Exception as e:
                logger.error(f"Error processing judgment {judgment.id}: {str(e)}")
                continue
                
        return processed_count

def generate_embeddings(batch_size: int = None):
    """
    Convenience function to generate embeddings for all pending judgments.
    
    Args:
        batch_size: Optional batch size override
    """
    generator = EmbeddingGenerator()
    processed = generator.process_pending_judgments(batch_size)
    logger.info(f"Finished processing {processed} judgments") 