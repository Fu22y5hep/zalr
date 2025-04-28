from semantis_app.models import Judgment
from openai import OpenAI
import os
import django
import time
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
import re

# Configure logging
logger = logging.getLogger(__name__)

django.setup()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
#client = OpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url="https://api.deepseek.com")

# Updated prompt template without bullet/number lists and without a system message
# Updated prompt template without text_here placeholders
PROMPT_TEMPLATE = """
Generate a markdown-formatted summary of the provided judgment using the following structure. Use proper markdown syntax including headers (#, ##, ###), emphasis (**bold**), and proper spacing:

# Case Note
[Provide the case name, citation, and date]

## Reportability
[Explain why this case is reportable and its significance]

## Cases Cited
[List the key cases referenced in the judgment]

## Legislation Cited
[List the relevant legislation referenced]

## Rules of Court Cited
[List any rules of court cited]

# HEADNOTE

## Summary
[Provide a concise summary of the case]

## Key Issues
[List the key legal issues addressed]

## Held
[Summarize the court's holding/findings]

# THE FACTS
[Provide a summary of the relevant facts]

# THE ISSUES
[Explain the legal questions the court had to decide]

# ANALYSIS
[Summarize the court's reasoning and analysis]

# REMEDY
[Describe the remedy or order given by the court]

# LEGAL PRINCIPLES
[Extract the key legal principles established or applied]

Please ensure each section:
1. Uses proper markdown headers (# for main sections, ## for subsections)
2. Includes at least 3 well-formed paragraphs where specified
3. Uses proper markdown formatting for emphasis (**bold** for important terms)
4. Maintains proper spacing between sections (one blank line after each section)
5. Uses proper citation formats
6. Presents information in clear paragraphs without bullet points or numbered lists

Full text:
{text}
"""

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_completion(prompt):
    """Generate completion with retry logic."""
    try:
        completion = client.chat.completions.create(
            model="o3-mini-2025-01-31",  # Using the specified model
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        return completion
    except Exception as e:
        logger.error(f"Error in API call: {str(e)}")
        raise  # Re-raise for retry

def clean_markdown(text: str) -> str:
    """
    Clean and format markdown text to ensure consistent styling.
    
    Args:
        text: The markdown text to clean
        
    Returns:
        str: Cleaned markdown text
    """
    # Ensure proper header formatting (space after #)
    text = re.sub(r'#([^#\s])', r'# \1', text)
    
    # Ensure one blank line before headers
    text = re.sub(r'([^\n])\n#', r'\1\n\n#', text)
    
    # Ensure proper bold formatting (no spaces inside **)
    text = re.sub(r'\*\* ([^*]+) \*\*', r'**\1**', text)
    
    # Remove multiple consecutive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Ensure proper citation formatting [YYYY] COURT XX
    text = re.sub(r'\[(\d{4})\]\s*([A-Z]+)\s*(\d+)', r'[\1] \2 \3', text)
    
    # Ensure proper section references (e.g., Section 1(2)(a))
    text = re.sub(r'section\s+(\d+)', r'Section \1', text, flags=re.IGNORECASE)
    
    # Remove any trailing whitespace
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    
    return text.strip()

def validate_markdown_structure(text: str) -> bool:
    """
    Validate that the markdown text contains all required sections.
    
    Args:
        text: The markdown text to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    required_sections = [
        '# Case Note',
        '## Reportability',
        '## Cases Cited',
        '## Legislation Cited',
        '# HEADNOTE',
        '## Summary',
        '## Key Issues',
        '## Held',
        '# THE FACTS',
        '# THE ISSUES',
        '# ANALYSIS',
        '# REMEDY',
        '# LEGAL PRINCIPLES'
    ]
    
    for section in required_sections:
        if section.lower() not in text.lower():
            logger.warning(f"Missing required section: {section}")
            return False
    
    return True

def summarize_judgments(target_court=None, batch_size=None, judgment_ids=None, force=False, min_reportability=75):
    """
    Generate summaries for high-scoring judgments.
    If target_court is provided, only process judgments from that court.
    If batch_size is provided, only process that many judgments.
    If judgment_ids is provided, process only those specific judgments.
    If force is True, regenerate summaries for judgments that already have them.
    """
    try:
        # If specific judgment IDs are provided, process those
        if judgment_ids:
            judgments = Judgment.objects.filter(id__in=judgment_ids)
            # If not forcing, only process those without long summaries
            if not force:
                judgments = judgments.filter(long_summary__isnull=True)
            # Only process judgments with sufficiently high reportability
            judgments = judgments.filter(reportability_score__gte=min_reportability)
            logger.info(f"Processing {len(judgment_ids)} specific judgments with reportability >= {min_reportability}")
        else:
            # Get all judgments with reportability score >= min_reportability and no summary
            judgments = Judgment.objects.filter(
                reportability_score__gte=min_reportability
            ).exclude(text_markdown__isnull=True).order_by('id')
            
            # If not forcing, only process those without long summaries
            if not force:
                judgments = judgments.filter(long_summary__isnull=True)

            # Apply court filter if provided
            if target_court:
                judgments = judgments.filter(court=target_court)
                
            # Apply batch size if provided using efficient database-level limiting
            if batch_size:
                judgments = judgments[:batch_size]

        total_judgments = len(list(judgments))
        logger.info(f"Found {total_judgments} judgments to summarize")

        successful = []
        failed = []

        # Process each judgment
        for i, judgment in enumerate(judgments, 1):
            try:
                citation = judgment.full_citation or f"Judgment {judgment.id}"
                logger.info(f"Processing judgment {i}/{total_judgments}: {citation}")

                if not judgment.text_markdown:
                    logger.warning(f"No text found for judgment: {citation}")
                    continue

                # Prepare the prompt with the judgment text
                prompt = PROMPT_TEMPLATE.format(text=judgment.text_markdown)

                try:
                    # Generate the completion with retry logic
                    completion = generate_completion(prompt)
                    
                    # Extract response
                    summary = completion.choices[0].message.content

                    # Clean and validate the markdown
                    summary = clean_markdown(summary)
                    
                    if not validate_markdown_structure(summary):
                        logger.error(f"Generated summary for {citation} is missing required sections")
                        failed.append(citation)
                        continue

                    # Update the judgment with the summary
                    judgment.long_summary = summary
                    judgment.save()

                    successful.append(citation)
                    logger.info(f"Successfully summarized judgment: {citation}")
                    
                    # Add a small delay between API calls
                    if i < total_judgments:  # Don't delay after the last judgment
                        time.sleep(2)

                except Exception as e:
                    failed.append(citation)
                    logger.error(f"Failed to generate summary for {citation}: {str(e)}")
                    continue

            except Exception as e:
                failed.append(citation)
                logger.error(f"Error processing judgment {citation}: {str(e)}")
                continue

        logger.info(f"Finished processing all judgments. Successful: {successful}, Failed: {failed}")
        logger.info(f"Summarization completed. Successful: {len(successful)}, Failed: {len(failed)}")
        
        return successful

    except Exception as e:
        logger.error(f"Fatal error in summarize_judgments: {str(e)}")
        return []

if __name__ == "__main__":
    summarize_judgments()
