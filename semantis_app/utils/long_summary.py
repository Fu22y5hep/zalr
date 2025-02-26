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
PROMPT_TEMPLATE = """
Generate a markdown-formatted summary of the provided judgment using the following structure. Use proper markdown syntax including headers (#, ##, ###), emphasis (**bold**), and proper spacing:

# Case Note
{text_here}

## Reportability
{text_here}

## Cases Cited
{text_here}

## Legislation Cited
{text_here}

## Rules of Court Cited
{text_here}

# HEADNOTE

## Summary
{text_here}

## Key Issues
{text_here}

## Held
{text_here}

# THE FACTS
{text_here}

# THE ISSUES
{text_here}

# ANALYSIS
{text_here}

# REMEDY
{text_here}

# LEGAL PRINCIPLES
{text_here}

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

def summarize_judgments(target_court=None):
    """
    Generate summaries for high-scoring judgments.
    If target_court is provided, only process judgments from that court.
    """
    try:
        # Get all judgments with reportability score >= 75 and no summary
        judgments = Judgment.objects.filter(
            reportability_score__gte=75,
            long_summary__isnull=True
        ).exclude(text_markdown__isnull=True)

        # Apply court filter if provided
        if target_court:
            judgments = judgments.filter(court=target_court)

        total_judgments = judgments.count()
        logger.info(f"Found {total_judgments} judgments to summarize")

        successful = 0
        failed = 0

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
                        failed += 1
                        continue

                    # Update the judgment with the summary
                    judgment.long_summary = summary
                    judgment.save()

                    successful += 1
                    logger.info(f"Successfully summarized judgment: {citation}")
                    
                    # Add a small delay between API calls
                    if i < total_judgments:  # Don't delay after the last judgment
                        time.sleep(2)

                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to generate summary for {citation}: {str(e)}")
                    continue

            except Exception as e:
                failed += 1
                logger.error(f"Error processing judgment {citation}: {str(e)}")
                continue

        logger.info(f"Finished processing all judgments. Successful: {successful}, Failed: {failed}")
        return successful

    except Exception as e:
        logger.error(f"Fatal error in summarize_judgments: {str(e)}")
        return 0

if __name__ == "__main__":
    summarize_judgments()
