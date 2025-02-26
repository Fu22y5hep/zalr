import re
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from django.db.models import Q
from ..models import Judgment
import logging

logger = logging.getLogger(__name__)

class MetadataParser:
    """
    Parser for extracting metadata from judgment text.
    Handles extraction of citation, court, case number, date, and judges.
    """
    
    # Common South African court codes - no longer mapping to full names
    COURT_CODES = {
        'ZACC',  # Constitutional Court
        'ZASCA',  # Supreme Court of Appeal
        'ZAGPJHC',  # Gauteng Local Division, Johannesburg
        'ZAGPPHC',  # Gauteng Division, Pretoria
        'ZAWCHC',  # Western Cape Division, Cape Town
        'ZAKZDHC',  # KwaZulu-Natal Division, Durban
        'ZAECG',  # Eastern Cape Division, Grahamstown
    }

    def __init__(self, text: str, title: Optional[str] = None):
        self.text = text
        self.title = title
        self.lines = text.split('\n')
        self.first_50_lines = '\n'.join(self.lines[:50])  # Most metadata is in the header

    def extract_all(self) -> Dict[str, any]:
        """
        Extract all metadata fields from the judgment text.
        First tries to parse from title, then falls back to full text search.
        """
        # First try to get metadata from title
        metadata = self.parse_title() if self.title else {}
        
        # For any missing fields, try to extract from the full text
        if not any(key in metadata for key in ['full_citation', 'neutral_citation_year', 'neutral_citation_number']):
            citation_data = self.extract_citation()
            if citation_data:
                metadata.update(citation_data)
        if 'court' not in metadata:
            metadata['court'] = self.extract_court()
        if 'case_number' not in metadata:
            metadata['case_number'] = self.extract_case_number()
        if 'judgment_date' not in metadata:
            metadata['judgment_date'] = self.extract_date()
        if 'judges' not in metadata:
            metadata['judges'] = self.extract_judges()
        
        return metadata

    def parse_title(self) -> Dict[str, any]:
        """
        Parse metadata from the title in the format:
        'Party v Party (Case No) [Year] Court No; Citations (Date)'
        
        Example:
        'Capitec Bank Limited v Commissioner for the South African Revenue Service 
        (CCT 209/22) [2024] ZACC 1; 2024 (7) BCLR 841 (CC); 2024 (4) SA 361 (CC); 
        84 SATC 369 (12 April 2024)'
        """
        if not self.title:
            return {}

        metadata = {}
        
        # Extract case number
        case_number_match = re.search(r'\(([A-Z]+\s*\d+/\d+)\)', self.title)
        if case_number_match:
            metadata['case_number'] = case_number_match.group(1)

        # Extract court, year, and neutral citation number
        neutral_citation_match = re.search(r'\[(\d{4})\]\s+([A-Z]+)\s+(\d+)', self.title)
        if neutral_citation_match:
            year, court_code, number = neutral_citation_match.groups()
            if court_code in self.COURT_CODES:
                metadata['court'] = court_code
                metadata['full_citation'] = f"[{year}] {court_code} {number}"
                metadata['neutral_citation_year'] = int(year)
                metadata['neutral_citation_number'] = int(number)

        # Extract date
        date_match = re.search(r'\((\d{1,2}\s+[A-Za-z]+\s+\d{4})\)', self.title)
        if date_match:
            try:
                date_str = date_match.group(1)
                metadata['judgment_date'] = datetime.strptime(date_str, '%d %B %Y').date()
            except ValueError:
                pass

        return metadata

    def extract_citation(self) -> Optional[Dict[str, any]]:
        """Extract the neutral citation and its components."""
        # Look for neutral citation pattern only
        citation_pattern = r'\[(\d{4})\]\s+([A-Z]+)\s+(\d+)'  # [2024] ZACC 31
        
        match = re.search(citation_pattern, self.first_50_lines)
        if match:
            year, court_code, number = match.groups()
            return {
                'full_citation': self.first_50_lines[match.start():match.end()].strip(),
                'neutral_citation_year': int(year),
                'neutral_citation_number': int(number)
            }
        
        return None

    def extract_court(self) -> Optional[str]:
        """Extract the court code from the judgment."""
        # First try to find court code
        for code in self.COURT_CODES:
            if re.search(rf'\b{code}\b', self.first_50_lines):
                return code
        
        # Look for court name in header and map to code
        court_patterns = [
            (r'CONSTITUTIONAL\s+COURT', 'ZACC'),
            (r'SUPREME\s+COURT\s+OF\s+APPEAL', 'ZASCA'),
            (r'GAUTENG.*JOHANNESBURG', 'ZAGPJHC'),
            (r'GAUTENG.*PRETORIA', 'ZAGPPHC'),
            (r'WESTERN\s+CAPE', 'ZAWCHC'),
            (r'KWAZULU-NATAL.*DURBAN', 'ZAKZDHC'),
            (r'EASTERN\s+CAPE.*GRAHAMSTOWN', 'ZAECG'),
        ]
        
        for pattern, code in court_patterns:
            if re.search(pattern, self.first_50_lines, re.IGNORECASE):
                return code
        
        return None

    def extract_case_number(self) -> Optional[str]:
        """Extract the case number from the judgment."""
        case_patterns = [
            r'Case\s+(?:No|Number)[:.]?\s*(\w+/\d+/\d+)',  # Case No: 123/2023
            r'Case\s+(?:No|Number)[:.]?\s*(\d+/\d+)',      # Case No: 123/23
            r'\b([A-Z]+\s+\d+/\d+)\b',                     # CCT 123/23
            r'\b(\d+/\d+/\d+)\b',                          # 123/2023/123
        ]
        
        for pattern in case_patterns:
            match = re.search(pattern, self.first_50_lines)
            if match:
                return match.group(1).strip()
        
        return None

    def extract_date(self) -> Optional[datetime.date]:
        """Extract the judgment date."""
        # Common date formats in South African judgments
        date_patterns = [
            (r'Date\s+of\s+Judgment:\s*(\d{1,2}\s+\w+\s+\d{4})', '%d %B %Y'),
            (r'Delivered\s+on:\s*(\d{1,2}\s+\w+\s+\d{4})', '%d %B %Y'),
            (r'Date:\s*(\d{1,2}\s+\w+\s+\d{4})', '%d %B %Y'),
            (r'(\d{1,2}\s+\w+\s+\d{4})', '%d %B %Y'),
            (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),
        ]
        
        for pattern, date_format in date_patterns:
            match = re.search(pattern, self.first_50_lines)
            if match:
                try:
                    return datetime.strptime(match.group(1), date_format).date()
                except ValueError:
                    continue
        
        return None

    def extract_judges(self) -> Optional[str]:
        """Extract the judges' names from the judgment."""
        # Common judicial titles and their variations
        JUDICIAL_TITLES = {
            'CJ': 'Chief Justice',
            'DCJ': 'Deputy Chief Justice',
            'ADCJ': 'Acting Deputy Chief Justice',
            'P': 'President',
            'JP': 'Judge President',
            'DJP': 'Deputy Judge President',
            'JA': 'Judge of Appeal',
            'AJA': 'Acting Judge of Appeal',
            'J': 'Judge',
            'AJ': 'Acting Judge'
        }
        
        # Words that might be mistaken for judge names but should be ignored
        IGNORE_WORDS = {
            'court', 'appeal', 'judgment', 'justice', 'rights', 'analysis',
            'high', 'supreme', 'constitutional', 'environmental', 'administrative',
            'chief', 'deputy', 'acting', 'president', 'judge', 'judges',
            'applicant', 'respondent', 'appellant', 'defendant', 'plaintiff',
            'party', 'parties', 'case', 'matter', 'hearing', 'order', 'judgment',
            'application', 'review', 'appeal', 'motion', 'petition', 'south',
            'african', 'africa', 'republic', 'state', 'government', 'minister',
            'department', 'director', 'general', 'public', 'private', 'company',
            'corporation', 'limited', 'ltd', 'pty', 'inc', 'incorporated',
            'association', 'society', 'trust', 'foundation', 'institute',
            'council', 'board', 'committee', 'commission', 'authority',
            'municipality', 'municipal', 'local', 'provincial', 'national',
            'federal', 'central', 'eastern', 'western', 'northern', 'southern',
            'upper', 'lower', 'high', 'supreme', 'constitutional', 'appeal',
            'district', 'regional', 'division', 'branch', 'section', 'unit',
            'predator', 'leopard', 'animal', 'other', 'first', 'second', 'third',
            'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
            'executor', 'estate', 'late', 'scheme', 'medical', 'profmed'
        }
        
        def is_valid_judge_name(name: str) -> bool:
            """Check if a name appears to be a valid judge name."""
            # Must end with a judicial title
            if not any(name.endswith(f" {title}") for title in JUDICIAL_TITLES):
                return False
                
            # Get the name part without the title
            name_part = re.sub(r'\s+(?:' + '|'.join(JUDICIAL_TITLES) + ')$', '', name).strip()
            
            # Convert to lowercase for checking against ignore words
            name_lower = name_part.lower()
            
            # Check if it's in the ignore list
            if name_lower in IGNORE_WORDS:
                return False
                
            # Check if any word in the name is in the ignore list
            if any(word.lower() in IGNORE_WORDS for word in name_part.split()):
                return False
                
            # Must be a reasonable length
            if len(name_part) < 3 or len(name_part) > 50:
                return False
                
            # Must contain at least one letter
            if not re.search(r'[A-Za-z]', name_part):
                return False
                
            return True
        
        def clean_text(text: str) -> str:
            """Clean text for better parsing."""
            # Remove markdown headers and formatting
            text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
            text = re.sub(r'\*\*.*?\*\*', '', text)  # Remove bold
            text = re.sub(r'_.*?_', '', text)        # Remove italics
            text = re.sub(r'\[.*?\]', '', text)      # Remove links
            
            # Convert multiple newlines to single newline
            text = re.sub(r'\n\s*\n', '\n', text)
            
            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text)
            
            # Remove multiple spaces after punctuation
            text = re.sub(r'([.,;:])\s+', r'\1 ', text)
            
            # Remove excessive spaces around parentheses
            text = re.sub(r'\s*\(\s*', '(', text)
            text = re.sub(r'\s*\)\s*', ') ', text)
            
            # Remove excessive spaces at line ends
            text = re.sub(r'\s+$', '', text, flags=re.MULTILINE)
            
            return text.strip()
        
        def normalize_judge_name(name: str) -> str:
            """Normalize a judge's name to handle variations."""
            # Remove any markdown or special characters
            name = re.sub(r'[*_\[\]`]', '', name)
            
            # Handle ALL CAPS
            if name.isupper():
                words = name.split()
                # Keep judicial titles in original form
                name = ' '.join(w if w in JUDICIAL_TITLES else w.title() for w in words)
            
            # Remove extra whitespace
            name = ' '.join(name.split())
            
            # Handle spaced titles (e.g., "A J" -> "AJ")
            for title in JUDICIAL_TITLES:
                # Try both spaced and unspaced versions
                spaced_title = ' '.join(title)
                if name.endswith(f" {spaced_title}"):
                    return name[:-len(spaced_title)-1] + f" {title}"
                elif name.endswith(spaced_title):
                    return name[:-len(spaced_title)] + title
                elif name.endswith(f" {title}"):
                    return name  # Already in correct format
                elif name.endswith(title):
                    return name[:-len(title)] + f" {title}"
            
            return name
        
        def extract_names_from_text(text: str) -> set:
            """Extract judge names from a text section using various patterns."""
            names = set()
            
            # Pattern to match judge sections
            judge_section_patterns = [
                # Standard formats
                r'(?:Before|Coram|Heard[ ]before|Judgment[ ]by|Delivered[ ]by|Written[ ]by|Present)[:.]?[ ]*(.*?)(?=\n[ ]*\n|\n[ ]*\[|\Z)',
                # Concurring format
                r'\[[\d ]+\][ ]*([A-Z][a-z]+(?:[ ]+[A-Z][a-z]+)*[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r'))[ ]*[\(:]',
                # List of judges format
                r'(?m)^([A-Z][a-z]+(?:[ ]+[A-Z][a-z]+)*[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r'))(?:[ ]*[,.]|$)',
                # ALL CAPS format
                r'(?m)^([A-Z]+(?:[ ]+[A-Z]+)*[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r'))(?:[ ]*[,.]|$)',
                # Judgment indicator
                r'Judgment[ ]of[ ]([A-Z][a-z]+(?:[ ]+[A-Z][a-z]+)*[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r'))',
                # Colon format
                r'([A-Z][a-z]+(?:[ ]+[A-Z][a-z]+)*[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r')):',
                # Parenthetical format
                r'\(([A-Z][a-z]+(?:[ ]+[A-Z][a-z]+)*[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r'))\)',
                # ALL CAPS with title
                r'([A-Z]+(?:[ ]+[A-Z]+)*[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r'))',
                # ALL CAPS name followed by title
                r'([A-Z]+(?:[ ]+[A-Z]+)+)[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r')',
                # Mixed case name with optional initials
                r'([A-Z][a-z]+(?:[ ]+(?:[A-Z]\.?|[A-Z][a-z]+))+[ ]+(?:' + '|'.join(JUDICIAL_TITLES) + r'))'
            ]
            
            for pattern in judge_section_patterns:
                matches = re.finditer(pattern, text, re.MULTILINE | re.DOTALL)
                for match in matches:
                    section = match.group(1).strip()
                    
                    # If section contains a colon, take the part after it
                    if ':' in section:
                        section = section.split(':', 1)[1].strip()
                    
                    # Split on common separators
                    parts = re.split(r'\s*(?:,|\band\b|&|;|\bet\s+al\b\.?)\s*', section)
                    
                    for part in parts:
                        judge = normalize_judge_name(part.strip())
                        if judge and is_valid_judge_name(judge):
                            names.add(judge)
            
            return names
        
        # Clean and prepare text sections
        text_sections = [
            clean_text(self.first_50_lines),  # Header section
            clean_text(self.text[:1000])  # First 1000 chars
        ]
        
        judges = set()  # Use a set to avoid duplicates
        
        # First try to find a dedicated judge section
        for text in text_sections:
            # Look for sections that might list judges
            section_headers = [
                r'(?:Judges?|Court|Bench|Panel|Coram|Present)[:.][ ]*(.*?)(?=\n\n|\n[A-Z]|\Z)',
                r'(?:Before|Heard[ ]before)[:.][ ]*(.*?)(?=\n\n|\n[A-Z]|\Z)',
                r'(?:Judgment|Order)[ ]by[:.][ ]*(.*?)(?=\n\n|\n[A-Z]|\Z)',
                r'(?:Delivered|Written)[ ]by[:.][ ]*(.*?)(?=\n\n|\n[A-Z]|\Z)'
            ]
            
            for header in section_headers:
                match = re.search(header, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                if match:
                    section = match.group(1).strip()
                    # Split on common separators
                    parts = re.split(r'\s*(?:,|\band\b|&|;|\bet\s+al\b\.?)\s*', section)
                    for part in parts:
                        judge = normalize_judge_name(part.strip())
                        if judge and is_valid_judge_name(judge):
                            judges.add(judge)
        
        # If we didn't find judges in a dedicated section, try pattern matching
        if not judges:
            for text in text_sections:
                judges.update(extract_names_from_text(text))
        
        # If we still found no judges, try the first paragraph after [1]
        if not judges:
            first_para_match = re.search(r'\[1\](.*?)(?=\[2\]|\Z)', self.text, re.DOTALL)
            if first_para_match:
                first_para = clean_text(first_para_match.group(1))
                judges.update(extract_names_from_text(first_para))
        
        # Convert set to sorted list and join
        judge_list = sorted(list(set(judges)))  # Extra set() to ensure no duplicates
        return ', '.join(judge_list) if judge_list else None

    @staticmethod
    def update_judgment_metadata(judgment: Judgment) -> bool:
        """
        Update a judgment's metadata by parsing its text and title.
        
        Args:
            judgment: The Judgment instance to update
            
        Returns:
            bool: True if any metadata was updated, False otherwise
        """
        if not judgment.text_markdown:
            return False
            
        parser = MetadataParser(judgment.text_markdown, judgment.title)
        metadata = parser.extract_all()
        
        # Track if any fields were updated
        updated = False
        
        for field, value in metadata.items():
            if value and not getattr(judgment, field):
                setattr(judgment, field, value)
                updated = True
        
        if updated:
            judgment.save()
            
        return updated

def process_missing_metadata(batch_size: int = 50) -> int:
    """
    Process judgments with missing metadata in batches.
    
    Args:
        batch_size: Number of judgments to process in each batch
        
    Returns:
        Number of judgments updated
    """
    try:
        # Get judgments with any missing metadata
        query = (
            Q(full_citation__isnull=True) |
            Q(court__isnull=True) |
            Q(case_number__isnull=True) |
            Q(judgment_date__isnull=True) |
            Q(judges__isnull=True)
        )
        
        judgments = Judgment.objects.filter(query)[:batch_size]
        total_judgments = judgments.count()
        logger.info(f"Found {total_judgments} judgments with missing metadata")
        
        updated_count = 0
        error_count = 0
        
        for i, judgment in enumerate(judgments, 1):
            try:
                logger.info(f"Processing judgment {i}/{total_judgments} (ID: {judgment.id})")
                if MetadataParser.update_judgment_metadata(judgment):
                    updated_count += 1
                    logger.info(f"Successfully updated metadata for judgment {judgment.id}")
                else:
                    logger.warning(f"No metadata updates needed for judgment {judgment.id}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing judgment {judgment.id}: {str(e)}")
                continue
        
        logger.info(f"Metadata processing complete. Updated: {updated_count}, Errors: {error_count}")
        return updated_count

    except Exception as e:
        logger.error(f"Error in process_missing_metadata: {str(e)}")
        return 0
