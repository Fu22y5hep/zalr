import os
# Set tokenizers parallelism to false to avoid deadlocks
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import sys
import django
import logging
from typing import Optional
import time
import argparse

# Add project root to Python path and setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalr_backend.settings')
django.setup()

from semantis_app.models import Judgment
from semantis_app.utils.llm_api import query_llm

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """You are an AI specialized in generating South African law headnotes.
Please read the following case text and produce a concise headnote in the style of the South African Law Reports.
The headnote must include only the crucial legal points, a summary of relevant facts, and the main holding. 

Maintain the structure of a headnote as follows:
1. Topic and subtopic, such as "Execution — Sale in execution — Notice …" 
2. Brief summary of the relevant facts
3. Legal issue
4. Holding/Conclusion

Please do not include any additional commentary or full citations; simply produce the essential legal points in the style of a reported case headnote. 

Case text:
{text}

Please provide only the summary, without any additional commentary or formatting.
Here is an example:
Execution — Sale in execution — Notice of sale in execution — Rule 46(7)(c) of Uniform Rules requiring publication of  H  notice in Gazette two weeks before date of appointed sale — Advertisement not placed timeously — Sheriff placing advertisement in Gazette one day short of two weeks before date of appointed sale — No evidence of prejudice to any affected parties — Failure to observe time requirements for publication in Gazette condonable and not constituting  I  defect fatal to validity of sale"""

def generate_short_summary(text: str) -> Optional[str]:
    try:
        # Print model information
        model = "gpt-4o-mini"
        provider = "openai"
        logger.info(f"Using LLM Model: {model} (Provider: {provider})")
        
        # Use OpenAI for generation
        response = query_llm(
            prompt=SUMMARY_PROMPT.format(text=text),
            provider=provider,
            model=model
        )
        
        if not response:
            logger.error("No response received from LLM")
            return None
            
        # Clean up the response
        summary = response.strip()
        # Remove any markdown formatting if present
        summary = summary.replace('#', '').replace('*', '')
        return summary
        
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        return None

def process_case(judgment: Judgment) -> bool:
    try:
        citation = judgment.full_citation or f"Judgment {judgment.id}"
        logger.info(f"Processing judgment: {citation}")
        
        if not judgment.text_markdown:
            logger.warning(f"No text found for judgment: {citation}")
            return False
            
        summary = generate_short_summary(judgment.text_markdown)
        if summary:
            judgment.short_summary = summary
            judgment.save()
            logger.info(f"Successfully generated summary for {citation}")
            return True
            
        logger.warning(f"Failed to generate summary for {citation}")
        return False
        
    except Exception as e:
        logger.error(f"Error processing judgment {citation}: {str(e)}")
        return False

def process_all_cases(batch_size: int = 20, delay: float = 2.0, force: bool = False, target_court: Optional[str] = None) -> int:
    try:
        # Get total count of judgments that need processing
        query = Judgment.objects.filter(text_markdown__isnull=False)
        if target_court:
            query = query.filter(court=target_court)
        if not force:
            query = query.filter(short_summary__isnull=True)
            
        total_judgments = query.count()
        
        if total_judgments == 0:
            logger.info("No judgments found that need processing")
            return 0
            
        logger.info(f"Found {total_judgments} judgments that need processing")
        logger.info(f"Processing batch of {batch_size} judgments")
        logger.info(f"Force mode: {'enabled' if force else 'disabled'}")
        if target_court:
            logger.info(f"Target court: {target_court}")
        
        # Get judgments without summaries
        judgments = query.order_by('judgment_date')[:batch_size]  # Process in batches
        
        total = len(judgments)
        successful = failed = 0
        
        for i, judgment in enumerate(judgments, 1):
            logger.info(f"Processing judgment {i} of {total} (Total remaining: {total_judgments - i})")
            if process_case(judgment):
                successful += 1
            else:
                failed += 1
            if i < total:
                time.sleep(delay)  # Delay between judgments
                
        logger.info(f"Processing completed. Successful: {successful}, Failed: {failed}")
        logger.info(f"Remaining judgments to process: {total_judgments - successful}")
        
        return successful
        
    except Exception as e:
        logger.error(f"Error in process_all_cases: {str(e)}")
        return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate short summaries for legal judgments')
    parser.add_argument('--batch-size', type=int, default=20,
                      help='Number of judgments to process (default: 20)')
    parser.add_argument('--delay', type=float, default=2.0,
                      help='Delay between processing judgments in seconds (default: 2.0)')
    parser.add_argument('--force', action='store_true',
                      help='Process all judgments, even those that already have summaries')
    parser.add_argument('--target-court', type=str,
                      help='Filter judgments by court')
    args = parser.parse_args()
    
    logger.info("Starting short summary generation process")
    logger.info("Configuration:")
    logger.info(f"- Batch size: {args.batch_size}")
    logger.info(f"- Delay between judgments: {args.delay} seconds")
    logger.info(f"- Force mode: {'enabled' if args.force else 'disabled'}")
    logger.info(f"- Target court: {args.target_court}")
    logger.info(f"- LLM Provider: openai")
    logger.info(f"- LLM Model: gpt-4o-mini")
    successful = process_all_cases(batch_size=args.batch_size, delay=args.delay, force=args.force, target_court=args.target_court)
    logger.info(f"Short summary generation process completed. Successful: {successful}")
