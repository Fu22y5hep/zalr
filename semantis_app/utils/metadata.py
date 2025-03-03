import re
import os
import yaml
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Set
from django.db.models import Q
from django.conf import settings
from ..models import Judgment
import logging
# Remove docling imports
# from .docling_processor import DoclingProcessor
# from docling.datamodel.document import DoclingDocument

logger = logging.getLogger(__name__)

class MetadataParser:
    """
    Parser for extracting metadata from judgment text.
    Handles extraction of citation, court, case number, date, and judges.
    """
    
    # Court codes and patterns loaded from YAML file
    _COURT_CODES = None
    _COURT_PATTERNS = None
    
    @classmethod
    def load_courts_from_yaml(cls) -> tuple:
        """
        Load court codes and names from the courts.yaml file.
        Returns a tuple of (court_codes_set, court_patterns_list)
        """
        try:
            yaml_path = os.path.join(settings.BASE_DIR, 'semantis_app', 'config', 'courts.yaml')
            logger.info(f"Loading courts from: {yaml_path}")
            
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = f.read()
            
            # Extract court codes and names using regex
            court_codes = set()
            court_patterns = []
            
            # Pattern to match court entries like "**Court Name** - CODE"
            pattern = r'\*\*(.*?)\*\*\s+–\s+([A-Z]+)'
            
            for match in re.finditer(pattern, data):
                court_name, court_code = match.groups()
                court_codes.add(court_code)
                
                # Create a regex pattern to match this court name in text
                # Convert the court name to a regex pattern
                name_pattern = court_name.replace(',', r'.*')  # Allow text between parts
                name_pattern = re.sub(r'\s+', r'\\s+', name_pattern)  # Match whitespace
                
                # Add to patterns list with the corresponding court code
                court_patterns.append((name_pattern, court_code))
            
            return court_codes, court_patterns
            
        except Exception as e:
            logger.error(f"Error loading courts from YAML: {str(e)}")
            return set(), []
    
    @classmethod
    def get_court_codes(cls) -> Set[str]:
        """Get the set of valid court codes"""
        if cls._COURT_CODES is None:
            cls._COURT_CODES, cls._COURT_PATTERNS = cls.load_courts_from_yaml()
        return cls._COURT_CODES
    
    @classmethod
    def get_court_patterns(cls) -> List[Tuple[str, str]]:
        """Get the list of court name patterns and their codes"""
        if cls._COURT_PATTERNS is None:
            cls._COURT_CODES, cls._COURT_PATTERNS = cls.load_courts_from_yaml()
        return cls._COURT_PATTERNS
    
    def __init__(self, text: str, title: Optional[str] = None):
        self.text = text
        self.title = title
        # Remove docling document creation
        # self.docling_doc = None
        
        # Try to create DoclingDocument for more accurate extraction
        # if text:
        #     doc_name = title if title else "judgment"
        #     self.docling_doc = DoclingProcessor.convert_html_to_docling(text, doc_name)
    
    def extract_all(self) -> Dict[str, any]:
        """Extract all metadata from judgment text"""
        metadata = {}
        
        # Extract metadata from title if available
        # This is the ONLY source for all metadata except judges
        if self.title:
            title_data = self.parse_title()
            metadata.update(title_data)
        
        # Do NOT fall back to text extraction for any fields except judges
        # The following lines have been removed to ensure we only use title-based extraction
        # for court, citation, case number, and date

        # Always extract judges from the main text, not from the title
        judges = self.extract_judges()
        if judges:
            metadata["judges"] = judges
        
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
        
        # Extract case name (parties) - find the part before the first case number or citation
        case_name_match = re.search(r'^(.*?)(?:\(\d+|\([A-Z]+\s+\d+|\[\d{4}\])', self.title)
        if case_name_match:
            case_name = case_name_match.group(1).strip()
            # Clean up case name
            case_name = re.sub(r'\s+', ' ', case_name)
            metadata['case_name'] = case_name
        
        # Extract neutral citation components [YYYY] COURT XX
        neutral_citation_match = re.search(r'\[(\d{4})\]\s+([A-Z]+)\s+(\d+)', self.title)
        if neutral_citation_match:
            year, court_code, number = neutral_citation_match.groups()
            
            if court_code in self.get_court_codes():
                metadata['court'] = court_code
                metadata['full_citation'] = f"[{year}] {court_code} {number}"
                metadata['neutral_citation_year'] = int(year)
                metadata['neutral_citation_number'] = int(number)
        
        # Extract case number patterns
        case_number_patterns = [
            r'\(([A-Z]+\s*\d+/\d+(?:/\d+)?)\)',  # (CCT 123/2022)
            r'\((\d+/\d+(?:/\d+)?)\)',           # (123/2022)
            r'Case\s+No\.?\s*(\d+/\d+(?:/\d+)?)', # Case No. 123/2022
            r'(\d+/\d+)(?:\s|\)|\]|$)'           # 123/2022 followed by space, bracket, or end
        ]
        
        for pattern in case_number_patterns:
            match = re.search(pattern, self.title)
            if match:
                metadata['case_number'] = match.group(1)
                break

        # Extract date - look for date at the end of the title
        date_patterns = [
            r'\((\d{1,2}\s+[A-Za-z]+\s+\d{4})\)',  # (12 April 2024)
            r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})$',      # At end of title with no parentheses
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, self.title)
            if date_match:
                try:
                    date_str = date_match.group(1)
                    metadata['judgment_date'] = datetime.strptime(date_str, '%d %B %Y').date()
                    break
                except ValueError:
                    continue

        return metadata

    def extract_citation(self) -> Optional[Dict[str, any]]:
        """Extract the neutral citation and its components."""
        # Look for neutral citation pattern only
        citation_pattern = r'\[(\d{4})\]\s+([A-Z]+)\s+(\d+)'  # [2024] ZACC 31
        
        match = re.search(citation_pattern, self.text)
        if match:
            year, court_code, number = match.groups()
            return {
                'full_citation': self.text[match.start():match.end()].strip(),
                'neutral_citation_year': int(year),
                'neutral_citation_number': int(number)
            }
        
        return None

    def extract_court(self) -> Optional[str]:
        """Extract the court code from the judgment."""
        # First try to find court code
        for code in self.get_court_codes():
            if re.search(rf'\b{code}\b', self.text):
                return code
        
        # Look for court name in header and map to code
        for pattern, code in self.get_court_patterns():
            if re.search(pattern, self.text, re.IGNORECASE):
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
            match = re.search(pattern, self.text)
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
            match = re.search(pattern, self.text)
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
            clean_text(self.text[:1000]),  # First 1000 chars
            clean_text(self.text[1000:2000]),  # Next 1000 chars
            clean_text(self.text[2000:3000]),  # Next 1000 chars
            clean_text(self.text[3000:4000]),  # Next 1000 chars
            clean_text(self.text[4000:5000]),  # Next 1000 chars
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
        Update a judgment's metadata fields by parsing its text.
        Returns True if any fields were updated.
        """
        try:
            if not judgment.text_markdown:
                logger.warning(f"No text available for judgment {judgment.id}")
                return False
                
            # Create metadata parser with text and title
            parser = MetadataParser(judgment.text_markdown, judgment.case_name)
            metadata = parser.extract_all()
            
            # Track if any fields were updated
            updated = False
            
            # Update fields if they're empty or if we have new data
            for field, value in metadata.items():
                if value and hasattr(judgment, field):
                    current_value = getattr(judgment, field)
                    if not current_value or (field in ['court', 'neutral_citation_year', 'neutral_citation_number']):
                        setattr(judgment, field, value)
                        updated = True
            
            if updated:
                judgment.save()
                logger.info(f"Updated metadata for judgment {judgment.id}")
            else:
                logger.info(f"No metadata updates needed for judgment {judgment.id}")
                
            return updated
                
        except Exception as e:
            logger.error(f"Error updating judgment metadata: {str(e)}")
            return False

def process_missing_metadata(batch_size: int = 50) -> int:
    """
    Process judgments with missing metadata fields.
    Returns the number of judgments updated.
    """
    try:
        # Find judgments with missing important metadata
        judgments = Judgment.objects.filter(
            Q(court__isnull=True) | 
            Q(neutral_citation_year__isnull=True) |
            Q(neutral_citation_number__isnull=True) |
            Q(case_number__isnull=True) |
            Q(judgment_date__isnull=True) |
            Q(judges__isnull=True)
        ).exclude(
            text_markdown__isnull=True
        )[:batch_size]
        
        updated_count = 0
        
        for judgment in judgments:
            updated = MetadataParser.update_judgment_metadata(judgment)
            if updated:
                updated_count += 1
        
        return updated_count
        
    except Exception as e:
        logger.error(f"Error processing missing metadata: {str(e)}")
        return 0
