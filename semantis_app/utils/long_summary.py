from semantis_app.models import Judgment
from openai import OpenAI
import os
import django
import time
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging
logger = logging.getLogger(__name__)

django.setup()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
#client = OpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url="https://api.deepseek.com")
# Updated prompt template without bullet/number lists and without a system message
PROMPT_TEMPLATE = """
Summarize the provided judgment in the following structured legal format, presented in paragraphs without numbered or bulleted lists. Use precise terminology and replicate the sections, headings, and order below:

**Case Note**:
Explain why the case is reportable (e.g., novel principles, application of existing law). MENTION KEY LEAGAL PRINCIPLES OR DOCTRINES THAT WERE APPLIED. Do not start the sentnece with "Thios case is reportable because..."

**Cases Cited**:
Identify all cases mentioned in the judgment. For each case, use the correct citation style (e.g., Case Name [Year] Court Abbreviation Volume/Report Page). Present them in paragraphs.

**Legislation Cited**:
List or describe any statutes or regulations referenced. For instance: Road Accident Fund Act Section 17(1)(b).

**Rules of Court Cited**:
List or describe any rules of court referenced. For instance: Rule 1.1(a) of the Rules of Court.


**HEADNOTE**:
**Summary**:
Include one or two paragraphs on the core claim and the outcome.
**Key Issues**:
Briefly phrase the main legal issues in question form, if relevant.
**Held**:
State, in concise terms, the ultimate holding or decision.

**THE FACTS**:
Give a comprehensice account of the facts in no less than three paragraphs, including the parties, essential events, claims, and any relevant procedural history.

**THE ISSUES**:
List the legal questions the court had to determine in paragraph form. For example, (1) Whether…, (2) Whether…

**ANALYSIS**:
Detail the court's reasoning for each issu comprehensively in no less than three paragraphs. Explain how the court applied legal principles to the facts in paragraph form.

**REMEDY**:
Explain the relief granted or the final order of the court (e.g., application dismissed with costs).

**LEGAL PRINCIPLES**:
Describe the key legal principles or rules that guided the court's decision comprehensively in no less than three paragraphs. Include any direct quotes from cases or statutes where necessary, but present them within paragraphs without bullet points.

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
