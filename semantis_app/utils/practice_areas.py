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
    "Administrative Law",
    "Commercial Law",
    "Competition Law",
    "Constitutional Law",
    "Criminal Law",
    "Delictual Law",
    "Environmental Law",
    "Family Law",
    "Insurance Law",
    "Intellectual Property Law",
    "Labour Law",
    "Land and Property Law",
    "Practice and Procedure",
    "Tax Law",
    "Arbitration"
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
        first_part = judgment_text[:2500]
        middle_start = len(judgment_text) // 2 - 1000
        middle_part = judgment_text[middle_start:middle_start + 2000]
        last_part = judgment_text[-1500:]
        sample_text = f"{first_part}\n...[text truncated]...\n{middle_part}\n...[text truncated]...\n{last_part}"
    
    prompt = f"""
You are a South African legal expert specializing in classifying court judgments into practice areas. Analyze the following court judgment and identify the most relevant legal practice areas it falls under.

The judgment text is:
\"\"\"{sample_text}\"\"\"

Available South African practice areas: {areas_str}

Identify only the 1-3 most relevant practice areas for this judgment from the list provided. Consider:
1. The primary legal issues addressed in the judgment
2. The legal principles and statutes applied
3. The subject matter of the dispute
4. The area of law that would be most interested in this judgment

Return your answer as a JSON object with:
1. A "practice_areas" field containing an ARRAY of the relevant practice areas, chosen ONLY from the provided list
2. A "reasoning" field explaining your classification:

{{
  "practice_areas": ["Area1", "Area2"],
  "reasoning": "This judgment deals with..."
}}

If you cannot confidently classify the judgment because it lacks sufficient legal content, return an empty practice_areas array and explain why in the reasoning.
"""
    return prompt

def classify_judgment(judgment: Judgment) -> Optional[Dict]:
    """
    Classify a single judgment into practice areas using the short summary.
    
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
            
        # If no short summary, we can't classify
        if not judgment.short_summary or len(judgment.short_summary.strip()) == 0:
            logger.warning(f"No short_summary available for judgment {judgment.id}")
            return None
        
        logger.info(f"Using short_summary for judgment {judgment.id}: {judgment.short_summary[:200]}...")
        
        # First try a simple word-matching approach based on the first word of the summary
        first_word = judgment.short_summary.strip().split()[0].strip('.:,;()[]{}').lower()
        logger.info(f"First word of summary: {first_word}")
        
        # Define mappings from common first words to practice areas
        word_to_practice_area = {
            # Administrative Law
            'administrative': 'Administrative Law',
            'review': 'Administrative Law',
            'paja': 'Administrative Law',
            
            # Commercial Law
            'contract': 'Commercial Law',
            'business': 'Commercial Law',
            'company': 'Commercial Law',
            'commercial': 'Commercial Law',
            'credit': 'Commercial Law',
            
            # Competition Law
            'competition': 'Competition Law',
            'antitrust': 'Competition Law',
            'merger': 'Competition Law',
            
            # Constitutional Law
            'constitutional': 'Constitutional Law',
            'constitution': 'Constitutional Law',
            'rights': 'Constitutional Law',
            
            # Criminal Law
            'criminal': 'Criminal Law',
            'sentence': 'Criminal Law',
            'bail': 'Criminal Law',
            'theft': 'Criminal Law',
            'murder': 'Criminal Law',
            'evidence': 'Criminal Law',
            
            # Delictual Law
            'delict': 'Delictual Law',
            'negligence': 'Delictual Law',
            'damages': 'Delictual Law',
            'defamation': 'Delictual Law',
            
            # Environmental Law
            'environmental': 'Environmental Law',
            'conservation': 'Environmental Law',
            
            # Family Law
            'family': 'Family Law',
            'divorce': 'Family Law',
            'custody': 'Family Law',
            'maintenance': 'Family Law',
            
            # Insurance Law
            'insurance': 'Insurance Law',
            'insurer': 'Insurance Law',
            'policy': 'Insurance Law',
            
            # Intellectual Property Law
            'intellectual': 'Intellectual Property Law',
            'copyright': 'Intellectual Property Law',
            'trademark': 'Intellectual Property Law',
            'patent': 'Intellectual Property Law',
            
            # Labour Law
            'labour': 'Labour Law',
            'labor': 'Labour Law',
            'employment': 'Labour Law',
            'dismissal': 'Labour Law',
            'employee': 'Labour Law',
            
            # Land and Property Law
            'property': 'Land and Property Law',
            'land': 'Land and Property Law',
            'eviction': 'Land and Property Law',
            'servitude': 'Land and Property Law',
            'lease': 'Land and Property Law',
            'tenant': 'Land and Property Law',
            
            # Practice and Procedure
            'procedure': 'Practice and Procedure',
            'costs': 'Practice and Procedure',
            'appeal': 'Practice and Procedure',
            'application': 'Practice and Procedure',
            'interlocutory': 'Practice and Procedure',
            'condonation': 'Practice and Procedure',
            'jurisdiction': 'Practice and Procedure',
            
            # Tax Law
            'tax': 'Tax Law',
            'taxation': 'Tax Law',
            'income': 'Tax Law',
            'vat': 'Tax Law',
            
            # Arbitration
            'arbitration': 'Arbitration',
            'arbitral': 'Arbitration'
        }
        
        # See if we can match based on the first word
        practice_areas = []
        if first_word in word_to_practice_area:
            practice_areas.append(word_to_practice_area[first_word])
            logger.info(f"Matched first word '{first_word}' to practice area: {practice_areas[0]}")
        
        # If no match by first word, look for key terms in the full summary
        if not practice_areas:
            summary_lower = judgment.short_summary.lower()
            # Look for practice area terms in the summary
            for key_term, area in word_to_practice_area.items():
                if key_term in summary_lower and area not in practice_areas:
                    practice_areas.append(area)
                    if len(practice_areas) >= 2:  # Limit to 2 practice areas max
                        break
        
        # If still no matches, use a fallback category
        if not practice_areas:
            # If the summary has "Road Accident Fund" or related terms
            if 'road accident' in judgment.short_summary.lower() or 'raf' in judgment.short_summary.lower():
                practice_areas.append('Delictual Law')
            else:
                # Use Practice and Procedure as a fallback if we really can't determine
                practice_areas.append('Practice and Procedure')
                logger.warning(f"No practice area match found, using fallback: Practice and Procedure")
        
        # Create a result dictionary with the classifications
        result = {
            "practice_areas": practice_areas,
            "reasoning": f"Classification based on short summary: {judgment.short_summary[:100]}..."
        }
        
        # Update the judgment
        judgment.practice_areas = ", ".join(result["practice_areas"])
        judgment.save()
        
        logger.info(f"Successfully classified judgment {judgment.id}: {judgment.practice_areas}")
        return result
            
    except Exception as e:
        logger.error(f"Error classifying judgment {judgment.id}: {str(e)}")
        return None

def classify_judgments(batch_size: int = 20, target_court: str = None, judgment_id: str = None) -> int:
    """
    Classify judgments into practice areas using short summaries.
    
    Args:
        batch_size: Number of judgments to process
        target_court: Optional court code to filter judgments
        judgment_id: Optional specific judgment ID to process
        
    Returns:
        Number of judgments successfully classified
    """
    try:
        logger.info(f"classify_judgments called with batch_size={batch_size}, target_court={target_court}, judgment_id={judgment_id}")
        
        # Build query for judgments without practice areas but with short summaries
        base_query = (Q(practice_areas__isnull=True) | Q(practice_areas="")) & ~Q(short_summary="") & ~Q(short_summary__isnull=True)
        
        # Add filters if provided
        if target_court:
            base_query &= Q(court=target_court)
            logger.info(f"Filtering for court: {target_court}")
            
        if judgment_id:
            # Process only the specific judgment
            logger.info(f"Processing specific judgment ID: {judgment_id}")
            try:
                judgment = Judgment.objects.get(id=judgment_id)
                # Debug the judgment we found
                logger.info(f"Found judgment with ID {judgment_id}, court={judgment.court}, year={judgment.neutral_citation_year}, practice_areas={judgment.practice_areas}")
                result = classify_judgment(judgment)
                return 1 if result else 0
            except Judgment.DoesNotExist:
                logger.error(f"Judgment with ID {judgment_id} not found")
                return 0
        
        # Get judgments to process
        judgments = Judgment.objects.filter(base_query)[:batch_size]
        judgment_count = judgments.count()
        logger.info(f"Found {judgment_count} judgments matching criteria for processing")
        
        classified_count = 0
        
        for judgment in judgments:
            try:
                with transaction.atomic():
                    logger.info(f"Processing judgment ID {judgment.id}, court={judgment.court}, year={judgment.neutral_citation_year}")
                    result = classify_judgment(judgment)
                    if result:
                        classified_count += 1
                        logger.info(f"Successfully classified judgment {judgment.id} as {judgment.practice_areas}")
                    else:
                        logger.warning(f"Failed to classify judgment {judgment.id}")
            except Exception as e:
                logger.error(f"Error processing judgment {judgment.id}: {str(e)}")
                continue
                
        logger.info(f"Practice area classification complete. Classified: {classified_count}")
        return classified_count
        
    except Exception as e:
        logger.error(f"Error in classify_judgments: {str(e)}")
        return 0 