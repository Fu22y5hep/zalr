import os
import re
from django.db import connection
from openai import OpenAI
from dotenv import load_dotenv
from django.db.models import Q
from semantis_app.models import Judgment, ScoringSection

# Load environment variables
load_dotenv()

# Debug: Print API key existence (not the key itself)
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OpenAI API key not found in environment variables")

# Configure OpenAI
client = OpenAI(api_key=api_key)

def get_unprocessed_cases(target_court=None):
    """Get cases that need reportability scores."""
    query = Judgment.objects.filter(
        reportability_score=0,
        text_markdown__isnull=False
    )
    
    if target_court:
        query = query.filter(court=target_court)
        
    return query.values_list('id', 'full_citation', 'text_markdown')

def save_reportability_score(case_id, score, explanation):
    """Save reportability score and explanation to database."""
    judgment = Judgment.objects.get(id=case_id)
    judgment.reportability_score = score
    judgment.reportability_explanation = explanation
    judgment.save()

def extract_category_scores(explanation: str) -> dict:
    """Extract individual category scores from the explanation."""
    categories = {
        'Legal Significance': 35,
        'Precedential Value': 25,
        'Practical Impact': 20,
        'Quality of Reasoning': 15,
        'Public Interest': 5
    }
    
    scores = {}
    for category in categories.keys():
        # Look for score patterns like "Score: 20/35" or "(20/35)"
        pattern = f"{category}.*?(?:Score:|\\()\\s*(\\d+)(?:/\\d+|\\s*\\))"
        match = re.search(pattern, explanation, re.IGNORECASE | re.DOTALL)
        if match:
            scores[category] = int(match.group(1))
    
    return scores

def validate_and_calculate_score(explanation: str) -> tuple[int, str]:
    """Validate category scores and calculate total score."""
    scores = extract_category_scores(explanation)
    
    # Calculate total score
    total_score = sum(scores.values())
    
    # Extract the reported total score
    score_match = re.search(r'Reportability Score:\s*(\d+)', explanation)
    reported_score = int(score_match.group(1)) if score_match else None
    
    # Add validation information to the explanation
    validation_info = "\n\n## Score Validation\n"
    validation_info += "Category Scores:\n"
    for category, score in scores.items():
        validation_info += f"- {category}: {score}\n"
    validation_info += f"\nCalculated Total: {total_score}"
    
    if reported_score is not None:
        validation_info += f"\nReported Score: {reported_score}"
        if total_score != reported_score:
            validation_info += f"\n⚠️ Warning: Reported score ({reported_score}) does not match calculated score ({total_score})"
            # Use the calculated score instead
            reported_score = total_score
    
    return total_score, explanation + validation_info

def analyze_text(text):
    """Generate reportability score using OpenAI."""
    if not text:
        print("Warning: Empty text provided to analyze_text")
        return None, None

    prompt = """Analyze the provided judgment and assign a 'reportability score' between 0 and 100. Be extremely strict in your scoring - only truly significant judgments should score above 75.

Your response MUST start with 'Reportability Score: XX' where XX is the numerical score.

Score the judgment based on these criteria, and be STRICT in your assessment:

1. **Legal Significance (Weight: 35)**:
   - High (30-35): Establishes new legal principle or significantly modifies existing law
   - Medium (20-29): Clarifies existing legal principles
   - Low (0-19): Merely applies established principles

2. **Precedential Value (Weight: 25)**:
   - High (20-25): From higher courts (Constitutional Court, SCA) AND likely to be widely cited
   - Medium (10-19): From high courts AND addresses important legal issues
   - Low (0-9): Limited precedential value or routine application of law

3. **Practical Impact (Weight: 20)**:
   - High (15-20): Major implications for legal practice or society at large
   - Medium (8-14): Moderate impact on specific legal areas
   - Low (0-7): Minimal practical impact beyond the parties involved

4. **Quality of Reasoning (Weight: 15)**:
   - High (12-15): Exceptional analysis, comprehensive research, novel legal insights
   - Medium (6-11): Sound reasoning but not exceptional
   - Low (0-5): Basic or flawed reasoning

5. **Public Interest (Weight: 5)**:
   - High (4-5): Significant public importance or media attention
   - Medium (2-3): Moderate public interest
   - Low (0-1): Limited public interest

IMPORTANT: Make sure your category scores add up to your total reportability score.

For each category, clearly state the score in this format: 'Score: XX/YY' where XX is the score given and YY is the maximum possible score for that category.

Example format:
Reportability Score: 85

1. Legal Significance (Weight: 35%)
Score: 30/35
[Explanation...]

[Continue with other categories...]"""

    try:
        # Debug: Print text length
        print(f"Analyzing text of length: {len(text)}")
        
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a highly critical legal expert analyzing court judgments. Be extremely strict in your scoring - only truly significant judgments should score above 75. Always start your response with 'Reportability Score: XX' where XX is a number between 0 and 100."},
                {"role": "user", "content": f"{prompt}\n\nHere is the judgment text:\n{text}"}
            ]
        )
        
        result = completion.choices[0].message.content
        print(f"Received response from OpenAI: {result[:200]}...")  # Debug: Print more of the response
        
        # Validate and calculate the correct score
        score, explanation = validate_and_calculate_score(result)
        return score, explanation
            
    except Exception as e:
        print(f"Error analyzing text: {str(e)}")
        print(f"Error type: {type(e)}")  # Debug: Print error type
        return None, None

def save_scoring_sections(case_id, explanation: str):
    """Save individual scoring sections to the database."""
    scores = extract_category_scores(explanation)
    judgment = Judgment.objects.get(id=case_id)
    
    for section_name, score in scores.items():
        # Extract explanation for this section from the full explanation
        section_pattern = f"{section_name}.*?Score: {score}/\\d+\\s*(.*?)(?=\\d+\\. \\*\\*|$)"
        section_match = re.search(section_pattern, explanation, re.DOTALL)
        section_explanation = section_match.group(1).strip() if section_match else ""
        
        ScoringSection.objects.create(
            judgment=judgment,
            section_name=section_name,
            score=score,
            explanation=section_explanation
        )

def process_cases(target_court=None, batch_size=None):
    """Process cases to generate reportability scores."""
    # Build the base query
    base_query = Q(reportability_score=0) & ~Q(text_markdown__isnull=True)
    
    # Apply court filter if provided
    if target_court:
        base_query &= Q(court=target_court)
    
    # Get the queryset and order it to ensure consistent results
    cases = Judgment.objects.filter(base_query).order_by('id')
    
    print(f"Found {cases.count()} cases to process")

    processed_count = 0
    
    # Apply batch size if provided using efficient database-level limiting
    if batch_size:
        cases = cases[:batch_size]
        print(f"Processing batch of {batch_size} cases")
    
    for case in cases:
        print(f"Processing case {case.id}")  # Debug: Print current case
        if case.text_markdown:  # Only process if we have text
            score, explanation = analyze_text(case.text_markdown)
            if score is not None:
                save_reportability_score(case.id, score, explanation)
                save_scoring_sections(case.id, explanation)
                processed_count += 1
                print(f"Processed case {case.id} with score {score}")
        else:
            print(f"Skipping case {case.id} - no text available")
    
    return processed_count

if __name__ == "__main__":
    process_cases()
