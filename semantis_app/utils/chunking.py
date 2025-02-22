from docling.chunking import HybridChunker
from docling_core.types import DoclingDocument
from dotenv import load_dotenv
from semantis_app.utils.tokenizer import VoyageTokenizerWrapper
import voyageai
from semantis_app.models import Judgment
from django.db.models import Q
from django.db import transaction
import logging
import uuid
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Initialize Voyage AI client (make sure you have VOYAGE_API_KEY in your environment variables)
client = voyageai.Client()

tokenizer = VoyageTokenizerWrapper()  # Load our custom tokenizer
MAX_TOKENS = 1000  # Maximum tokens per chunk
MIN_CHUNK_SIZE = 500  # Minimum characters per chunk
MAX_CHUNK_SIZE = 2000  # Maximum characters per chunk

def split_into_sections(text: str) -> list:
    """
    Split markdown text into sections based on headers and paragraphs.
    """
    # Split on markdown headers and paragraph breaks
    sections = []
    current_section = []
    current_size = 0
    
    # First split by headers
    header_sections = re.split(r'(?=# )', text)
    
    for section in header_sections:
        # Then split each header section by paragraphs
        paragraphs = re.split(r'\n\n+', section)
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            para_size = len(para)
            
            # If paragraph is too large, split it into sentences
            if para_size > MAX_CHUNK_SIZE:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current_text = ""
                
                for sentence in sentences:
                    if len(current_text) + len(sentence) > MAX_CHUNK_SIZE:
                        if current_text:
                            sections.append(current_text)
                        current_text = sentence
                    else:
                        current_text = current_text + " " + sentence if current_text else sentence
                
                if current_text:
                    sections.append(current_text)
                    
            # If adding this paragraph would exceed max size, start new section
            elif current_size + para_size > MAX_CHUNK_SIZE:
                if current_section:
                    sections.append('\n\n'.join(current_section))
                current_section = [para]
                current_size = para_size
            else:
                current_section.append(para)
                current_size += para_size
    
    # Add any remaining section
    if current_section:
        sections.append('\n\n'.join(current_section))
    
    return sections

def merge_small_sections(sections: list, min_size: int = MIN_CHUNK_SIZE) -> list:
    """
    Merge sections that are too small.
    """
    merged = []
    current = []
    current_size = 0
    
    for section in sections:
        section_size = len(section)
        
        # If section is already big enough, add it directly
        if section_size >= min_size:
            if current:
                merged.append('\n\n'.join(current))
                current = []
                current_size = 0
            merged.append(section)
            continue
            
        # If adding this section would exceed max size, start new merged section
        if current_size + section_size > MAX_CHUNK_SIZE:
            if current:
                merged.append('\n\n'.join(current))
            current = [section]
            current_size = section_size
        else:
            current.append(section)
            current_size += section_size
            
            # If we've reached minimum size, add the merged section
            if current_size >= min_size:
                merged.append('\n\n'.join(current))
                current = []
                current_size = 0
    
    # Add any remaining sections
    if current:
        if len(current) == 1 and current_size < min_size:
            # If only one small section left, append to last merged section if possible
            if merged and len(merged[-1]) + current_size <= MAX_CHUNK_SIZE:
                merged[-1] = merged[-1] + '\n\n' + current[0]
            else:
                merged.append('\n\n'.join(current))
        else:
            merged.append('\n\n'.join(current))
    
    return merged

def process_pending_judgments() -> int:
    """
    Fetch all judgments that don't have chunks yet and create chunks for them.
    
    Returns:
        int: Number of judgments processed
    """
    # Get all judgments that don't have chunks yet
    pending_judgments = Judgment.objects.filter(chunks__isnull=True)
    total_judgments = pending_judgments.count()
    logger.info(f"Found {total_judgments} judgments to process")
    
    processed_count = 0
    error_count = 0
    
    for i, judgment in enumerate(pending_judgments, 1):
        try:
            logger.info(f"Processing judgment {i}/{total_judgments} (ID: {judgment.id})")
            
            # Basic validation
            if not judgment.text_markdown:
                logger.warning(f"Judgment {judgment.id} has no text_markdown content, skipping")
                continue
                
            chunks = chunk_judgment(judgment.id)
            if chunks:
                processed_count += 1
                logger.info(f"Successfully created {len(chunks)} chunks for judgment {judgment.id}")
            
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing judgment {judgment.id}: {str(e)}", exc_info=True)
            continue
    
    logger.info(f"Processing complete. Processed: {processed_count}, Errors: {error_count}")
    return processed_count

def chunk_judgment(judgment_id: str) -> list:
    """
    Get markdown text from a Judgment, chunk it, and save chunks directly to the judgment.
    
    Args:
        judgment_id: UUID of the judgment
        
    Returns:
        list: List of created chunks
    """
    try:
        judgment = Judgment.objects.get(id=judgment_id)
        
        # Check if judgment already has chunks
        if judgment.chunks is not None:
            logger.warning(f"Judgment {judgment_id} already has chunks")
            return judgment.chunks
        
        logger.info(f"Chunking text for judgment {judgment_id} (length: {len(judgment.text_markdown)})")
        chunks = chunk_markdown_text(judgment.text_markdown, judgment.title)
        
        # Save chunks directly to judgment
        with transaction.atomic():
            judgment.chunks = [
                {
                    'content': chunk,
                    'index': i
                }
                for i, chunk in enumerate(chunks)
                if chunk.strip()  # Skip empty chunks
            ]
            judgment.chunks_embedded = False  # Reset embedded status
            judgment.save()
        
        logger.info(f"Saved {len(judgment.chunks)} chunks for judgment {judgment_id}")
        return judgment.chunks
        
    except Judgment.DoesNotExist:
        raise ValueError(f"Judgment with id {judgment_id} not found")
    except Exception as e:
        logger.error(f"Error in chunk_judgment for {judgment_id}: {str(e)}", exc_info=True)
        raise

def chunk_markdown_text(markdown_text: str, doc_name: str = None) -> list:
    """
    Takes markdown text and returns a list of chunks.
    
    Args:
        markdown_text (str): The markdown text to chunk
        doc_name (str): Name for the document (required by DoclingDocument)
        
    Returns:
        list: A list of text chunks
    """
    try:
        # Create a Document object with required name field
        if doc_name is None:
            doc_name = f"doc_{uuid.uuid4()}"
        
        # First split into logical sections
        sections = split_into_sections(markdown_text)
        
        # Merge small sections while respecting max size
        merged_sections = merge_small_sections(sections)
        
        if not merged_sections:
            # If no sections were created, split text into fixed-size chunks
            text_length = len(markdown_text)
            chunk_size = min(MAX_CHUNK_SIZE, max(MIN_CHUNK_SIZE, text_length // 10))
            
            chunks = []
            for i in range(0, text_length, chunk_size):
                chunk = markdown_text[i:i + chunk_size]
                if chunk.strip():
                    chunks.append(chunk)
            
            logger.info(f"Created {len(chunks)} fixed-size chunks")
            return chunks
        
        logger.info(f"Created {len(merged_sections)} chunks")
        return merged_sections
        
    except Exception as e:
        logger.error(f"Error in chunk_markdown_text: {str(e)}", exc_info=True)
        raise