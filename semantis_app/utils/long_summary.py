from semantis_app.models import Judgment
from openai import OpenAI
import os
import django
import time
from tenacity import retry, stop_after_attempt, wait_exponential

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
            model="gpt-4o-mini",  # Using the specified model
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        return completion
    except Exception as e:
        print(f"Error in API call: {str(e)}")
        raise  # Re-raise for retry

def summarize_judgments(target_court=None):
    """
    Generate summaries for high-scoring judgments.
    If target_court is provided, only process judgments from that court.
    """
    # Get all judgments with reportability score >= 75 and no summary
    judgments = Judgment.objects.filter(
        reportability_score__gte=75,
        long_summary__isnull=True
    ).exclude(text_markdown__isnull=True)

    # Apply court filter if provided
    if target_court:
        judgments = judgments.filter(court=target_court)

    print(f"Found {judgments.count()} judgments to summarize")

    # Process each judgment
    for judgment in judgments:
        try:
            print(f"Processing judgment: {judgment.neutral_citation}")

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

                print(f"Successfully summarized judgment: {judgment.neutral_citation}")
                
                # Add a small delay between API calls
                time.sleep(2)

            except Exception as e:
                print(f"Failed to generate summary after retries for {judgment.neutral_citation}: {str(e)}")
                continue

        except Exception as e:
            print(f"Error processing judgment {judgment.neutral_citation}: {str(e)}")
            continue

    print("Finished processing all judgments")

if __name__ == "__main__":
    summarize_judgments()
