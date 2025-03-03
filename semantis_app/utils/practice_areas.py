import logging
import json
from typing import List, Dict, Optional
import re
from django.db import transaction
from django.db.models import Q

from ..models import Judgment
from .llm_api import generate_completion, LLMException
from .docling_processor import DoclingProcessor
from docling.datamodel.document import DoclingDocument

logger = logging.getLogger(__name__)

# Define practice areas
PRACTICE_AREAS = [
    "Constitutional Law",
    "Criminal Law",
    "Family Law",
    "Property Law",
    "Administrative Law",
    "Employment Law",
    "Corporate Law",
    "Tax Law",
    "Contract Law",
    "Commercial Law",
    "Civil Procedure", 
    "Intellectual Property",
    "Competition Law",
    "Banking and Finance",
    "Insurance Law",
    "Environmental Law",
    "Human Rights Law",
    "Immigration Law",
    "International Law",
    "Maritime Law"
]

def get_prompt_for_classification(judgment_text: str, areas: List[str]) -> str:
    """
    Generate a prompt for classification of legal text into practice areas.
    
    Args:
        judgment_text: Text of the judgment
        areas: List of practice areas to choose from
        
    Returns:
        Prompt for the LLM
    """
    # Format all possible areas as a comma-separated string
    areas_str = ", ".join(areas)
    
    # Create truncated text sample if text is too long (OpenAI has token limits)
    # Take beginning, middle and end sections
    sample_text = judgment_text
    if len(judgment_text) > 6000:
        first_part = judgment_text[:2000]
        middle_start = len(judgment_text) // 2 - 1000
        middle_part = judgment_text[middle_start:middle_start + 2000]
        last_part = judgment_text[-2000:]
        sample_text = f"{first_part}\n...[text truncated]...\n{middle_part}\n...[text truncated]...\n{last_part}"
    
    prompt = f"""
You are a legal expert analyst. Analyze the following court judgment and identify which legal practice areas it falls under.

The judgment text is:
\"\"\"{sample_text}\"\"\"

Available practice areas: {areas_str}

Identify the top 1-3 most relevant practice areas for this judgment. Consider:
1. The primary legal issues addressed
2. The legal principles and statutes applied
3. The subject matter of the dispute

Return your answer as a JSON object with a "practice_areas" field containing an array of the relevant practice areas, and a "reasoning" field explaining your classification:

{{
  "practice_areas": ["Area1", "Area2"],
  "reasoning": "This judgment primarily deals with..."
}}
"""
    return prompt

def classify_judgment(judgment: Judgment) -> Optional[Dict]:
    """
    Classify a single judgment into practice areas using LLM.
    
    Args:
        judgment: The judgment to classify
        
    Returns:
        Dictionary with classification results or None if failed
    """
    try:
        # Skip if already classified
        if judgment.practice_areas and len(judgment.practice_areas.strip()) > 0:
            logger.info(f"Judgment {judgment.id} already has practice areas: {judgment.practice_areas}")
            return None
            
        # Skip if no text
        if not judgment.text_markdown or len(judgment.text_markdown.strip()) == 0:
            logger.warning(f"No text available for judgment {judgment.id}")
            return None
        
        # Try using Docling for better text extraction
        docling_doc = None
        doc_name = judgment.case_name if judgment.case_name else f"judgment_{judgment.id}"
        docling_doc = DoclingProcessor.convert_html_to_docling(judgment.text_markdown, doc_name)
        
        # Use either Docling-extracted text or original text
        judgment_text = DoclingProcessor.get_document_text(docling_doc) if docling_doc else judgment.text_markdown
            
        # Generate prompt for classification
        prompt = get_prompt_for_classification(judgment_text, PRACTICE_AREAS)
        
        # Use OpenAI API to get classification
        model = "gpt-4o-mini"  # Use the default model as specified in the instructions
        response = generate_completion(
            prompt=prompt,
            model=model,
            max_tokens=500,
            temperature=0.2,  # Low temperature for consistent results
            response_format={"type": "json_object"}
        )
        
        # Parse the response
        try:
            result = json.loads(response)
            
            # Validate the result has expected fields
            if not isinstance(result.get("practice_areas"), list):
                logger.error(f"Invalid response format for judgment {judgment.id}: {response}")
                return None
                
            # Update the judgment
            judgment.practice_areas = ", ".join(result["practice_areas"])
            judgment.practice_areas_reasoning = result.get("reasoning", "")
            judgment.save()
            
            logger.info(f"Successfully classified judgment {judgment.id}: {judgment.practice_areas}")
            return result
            
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON response for judgment {judgment.id}: {response}")
            return None
            
    except LLMException as e:
        logger.error(f"LLM API error for judgment {judgment.id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error classifying judgment {judgment.id}: {str(e)}")
        return None

def classify_judgments(batch_size: int = 20, target_court: str = None, judgment_id: str = None) -> int:
    """
    Classify judgments into practice areas.
    
    Args:
        batch_size: Number of judgments to process
        target_court: Optional court code to filter judgments
        judgment_id: Optional specific judgment ID to process
        
    Returns:
        Number of judgments successfully classified
    """
    try:
        # Build query for judgments without practice areas
        base_query = Q(practice_areas__isnull=True) | Q(practice_areas="")
        
        # Add filters if provided
        if target_court:
            base_query &= Q(court=target_court)
            
            # Special handling for ZANWHC court
            if target_court == 'ZANWHC':
                logger.info("Special handling for North West High Court (ZANWHC)")
                # Force retry for any ZANWHC judgments that couldn't be classified
                base_query |= Q(court=target_court)
            
        if judgment_id:
            # Process only the specific judgment
            try:
                judgment = Judgment.objects.get(id=judgment_id)
                result = classify_judgment(judgment)
                return 1 if result else 0
            except Judgment.DoesNotExist:
                logger.error(f"Judgment with ID {judgment_id} not found")
                return 0
        
        # Get judgments to process
        judgments = Judgment.objects.filter(base_query)[:batch_size]
        
        # If no judgments found, try to find by just court (in case of partial metadata)
        if judgments.count() == 0 and target_court:
            logger.warning(f"No unclassified judgments found for {target_court}. Checking if any exist at all.")
            any_judgments = Judgment.objects.filter(court=target_court).count()
            if any_judgments > 0:
                logger.info(f"Found {any_judgments} judgments for {target_court}, but all have practice areas already.")
                # Force reclassify some anyway if it's ZANWHC (since we had issues with it)
                if target_court == 'ZANWHC':
                    logger.info("Forcing reclassification of some ZANWHC judgments.")
                    judgments = Judgment.objects.filter(court=target_court)[:batch_size]
        
        classified_count = 0
        
        for judgment in judgments:
            try:
                with transaction.atomic():
                    result = classify_judgment(judgment)
                    if result:
                        classified_count += 1
            except Exception as e:
                logger.error(f"Error processing judgment {judgment.id}: {str(e)}")
                continue
                
        logger.info(f"Practice area classification complete. Classified: {classified_count}")
        return classified_count
        
    except Exception as e:
        logger.error(f"Error in classify_judgments: {str(e)}")
        return 0 