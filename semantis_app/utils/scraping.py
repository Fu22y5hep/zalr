import requests
import re
from time import sleep
from docling.document_converter import DocumentConverter
from typing import List, Optional
from ..models import Judgment

class ScrapingError(Exception):
    """Custom exception for scraping-related errors"""
    pass

def clean_judgment_text(text: str) -> str:
    """
    Clean the judgment text by removing common SAFLII header content and other unwanted elements.
    """
    # Split text into lines
    lines = text.split('\n')
    
    # Find where the actual judgment content starts
    start_idx = 0
    for i, line in enumerate(lines):
        # Skip past the common header elements
        if any(header in line for header in [
            "About SAFLII",
            "Databases",
            "Search",
            "Terms of Use",
            "RSS Feeds",
            "<!-- image -->",
            "[Home]",  # Sometimes appears in navigation
            "[Databases]",  # Sometimes appears in navigation
            "[Search]",  # Sometimes appears in navigation
            "[Noteup]",  # Sometimes appears in navigation
        ]):
            start_idx = i + 1
            continue
        # If we find a line that looks like the start of the judgment, break
        if re.match(r'^.*\[\d{4}\].*\d+.*$', line):  # Matches citation format
            break
    
    # Join the remaining lines
    cleaned_text = '\n'.join(lines[start_idx:])
    
    # Remove multiple consecutive empty lines
    cleaned_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_text)
    
    return cleaned_text.strip()

def extract_court(citation: str) -> Optional[str]:
    """Extract court identifier from citation"""
    match = re.search(r'\[.*?\]\s+(\w+)\s+\d+', citation)
    return match.group(1) if match else None

def extract_judgment_date(citation: str) -> Optional[str]:
    """Extract judgment date from citation"""
    match = re.search(r'\((\d+\s+\w+\s+\d{4})\)', citation)
    return match.group(1) if match else None

def get_saflii_citations(url: str, target_court: Optional[str] = None) -> List[str]:
    """
    Get citations from SAFLII. Works for both list pages and single case pages.
    If target_court is provided, only returns citations from that court.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.saflii.org/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8",
    }
    resp = requests.get(url, headers=headers)
    html = resp.text

    print(f"\nFetching URL: {url}")
    print(f"Response status code: {resp.status_code}")

    citations = []
    
    # Look for citations in the make-database list items
    pattern = r'<li class="make-database"><a[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
    citations = [m.strip() for m in matches if m.strip()]
    
    if not citations:
        # If no list items found, try single case patterns
        single_case_pattern = r'<h2>\s*(.*?)\s*</h2>'
        single_case_match = re.search(single_case_pattern, html, re.IGNORECASE | re.DOTALL)
        if single_case_match:
            citation = single_case_match.group(1).strip()
            if not citation.startswith('20'):  # Skip year headings
                citations = [citation]

    # Filter citations by court if target_court is provided
    if target_court:
        citations = [c for c in citations if target_court in c]

    return citations

def get_case_url(citation: str, court: str, year: int) -> Optional[str]:
    """Generate URL from citation"""
    # Extract case number
    match = re.search(rf'\[{year}\]\s+{court}\s+(\d+)', citation)
    if match:
        number = match.group(1)
        return f"https://www.saflii.org/za/cases/{court}/{year}/{number}.html"
    return None

def scrape_court_year(court: str, year: int, single_case_url: Optional[str] = None) -> List[Judgment]:
    """
    Scrape all judgments from a specific court and year.
    
    Args:
        court: Court code (e.g., 'ZACC' for Constitutional Court)
        year: Year to scrape (e.g., 2024)
        single_case_url: Optional URL for scraping a single case
        
    Returns:
        List of created Judgment objects
    """
    try:
        if single_case_url:
            print(f"\nScraping single case from {single_case_url}")
            # For single case, we'll use the URL directly
            base_url = single_case_url
            citations = get_saflii_citations(base_url, target_court=court)
        else:
            base_url = f"https://www.saflii.org/za/cases/{court}/{year}/"
            print(f"\nScraping {court} judgments from {year}")
            citations = get_saflii_citations(base_url, target_court=court)
        
        if not citations:
            print(f"No cases found for {court} {year}")
            return []
        
        print(f"\nFound {len(citations)} cases to process\n")
        
        # Use docling's DocumentConverter
        converter = DocumentConverter()
        judgments = []
        
        for citation in citations:
            try:
                if single_case_url:
                    url = single_case_url
                else:
                    url = get_case_url(citation, court, year)
                    
                if not url:
                    print(f"Could not generate URL for citation: {citation}")
                    continue
                    
                print(f"\nProcessing: {citation}")
                print(f"Source: {url}")
                
                # Check if judgment already exists
                if Judgment.objects.filter(saflii_url=url).exists():
                    print(f"Judgment already exists: {citation}")
                    continue
                
                # Convert document using docling
                result = converter.convert(url)
                document = result.document
                
                if not document:
                    print(f"Failed to convert document: {citation}")
                    continue
                
                # Get markdown text and clean it
                md_text = document.export_to_markdown()
                cleaned_text = clean_judgment_text(md_text)
                
                # Create judgment
                judgment = Judgment.objects.create(
                    title=citation,
                    text_markdown=cleaned_text,
                    saflii_url=url
                )
                
                judgments.append(judgment)
                print(f"Successfully processed: {citation}")
                
                # Be nice to the server
                sleep(2)
                
            except Exception as e:
                print(f"Error processing case {citation}: {str(e)}")
                continue
        
        print(f"\nSuccessfully converted {len(judgments)} out of {len(citations)} judgments.")
        return judgments

    except Exception as e:
        raise ScrapingError(f"Error processing court {court} year {year}: {str(e)}") 