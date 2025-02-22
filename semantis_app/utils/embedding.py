import os
import numpy as np
from typing import List, Dict, Any
import voyageai
from dotenv import load_dotenv
from django.db import transaction
from semantis_app.models import TextChunk, Judgment
import time

load_dotenv()

class EmbeddingGenerator:
    """
    Handles the generation of embeddings for text chunks using voyage-law-2.
    """
    
    def __init__(self):
        """Initialize the Voyage AI client and set up configuration."""
        self.client = voyageai.Client()
        self.model = "voyage-law-2"
        self.batch_size = 10  # Number of chunks to process in one batch
        self.sleep_time = 1  # Time to sleep between batches to avoid rate limits
    
    def process_pending_chunks(self, batch_size: int = None) -> int:
        """
        Process all chunks that haven't been embedded yet.
        
        Args:
            batch_size: Optional override for batch size
            
        Returns:
            int: Number of chunks processed
        """
        if batch_size:
            self.batch_size = batch_size
            
        processed_count = 0
        
        # Get chunks that haven't been embedded yet
        pending_chunks = TextChunk.objects.filter(is_embedded=False).order_by('judgment', 'chunk_index')
        
        # Process in batches
        while True:
            batch = list(pending_chunks[:self.batch_size])
            if not batch:
                break
                
            try:
                self._process_batch(batch)
                processed_count += len(batch)
                print(f"Processed {processed_count} chunks so far")
                time.sleep(self.sleep_time)  # Be nice to the API
            except Exception as e:
                print(f"Error processing batch: {str(e)}")
                # Continue with next batch even if one fails
                continue
                
        return processed_count
    
    def _process_batch(self, chunks: List[TextChunk]):
        """
        Process a batch of chunks: generate embeddings and save to database.
        
        Args:
            chunks: List of TextChunk objects to process
        """
        # Extract text content from chunks
        texts = [chunk.content for chunk in chunks]
        
        # Generate embeddings
        try:
            embeddings = self.client.embed(texts, model=self.model)
        except Exception as e:
            print(f"Error generating embeddings: {str(e)}")
            raise
        
        # Save embeddings and update chunks in a transaction
        with transaction.atomic():
            for chunk, embedding in zip(chunks, embeddings):
                # Convert embedding to numpy array for pgvector
                embedding_array = np.array(embedding)
                
                # Update the judgment's embedding (average of its chunks)
                self._update_judgment_embedding(chunk.judgment, embedding_array)
                
                # Mark chunk as embedded
                chunk.is_embedded = True
                chunk.save()
    
    def _update_judgment_embedding(self, judgment: Judgment, new_embedding: np.ndarray):
        """
        Update a judgment's embedding by averaging all its chunk embeddings.
        
        Args:
            judgment: Judgment object to update
            new_embedding: New embedding to incorporate
        """
        # Get current embedding if it exists
        current_embedding = judgment.vector_embedding
        
        if current_embedding is None:
            # First chunk, just use its embedding
            judgment.vector_embedding = new_embedding
        else:
            # Average with existing embedding
            embedded_chunks_count = judgment.chunks.filter(is_embedded=True).count()
            judgment.vector_embedding = (current_embedding * embedded_chunks_count + new_embedding) / (embedded_chunks_count + 1)
        
        judgment.save()

def generate_embeddings(batch_size: int = None):
    """
    Convenience function to generate embeddings for all pending chunks.
    
    Args:
        batch_size: Optional batch size override
    """
    generator = EmbeddingGenerator()
    processed = generator.process_pending_chunks(batch_size)
    print(f"Finished processing {processed} chunks") 