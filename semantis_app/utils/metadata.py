import re
import os
import yaml
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Set
from django.db.models import Q
from django.conf import settings
from ..models import Judgment
import logging

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
                court_patterns.append((rf'{name_pattern}', court_code))
            
            logger.info(f"Loaded {len(court_codes)} court codes from YAML file")
            return court_codes, court_patterns
            
        except Exception as e:
            logger.error(f"Error loading courts from YAML: {str(e)}")
            # Fallback to hardcoded values if YAML loading fails
            fallback_codes = {
                'ZACC', 'ZASCA', 'ZAGPJHC', 'ZAGPPHC', 'ZAWCHC', 'ZAKZDHC', 'ZAKZPHC',
                'ZAECGHC', 'ZAECPEHC', 'ZAECMHC', 'ZAFSHC', 'ZANWHC', 'ZALMPPHC',
                'ZAMPUMALANGA', 'ZANCHC', 'ZALAC', 'ZALCJHB', 'ZALCCT', 'ZALCDBN', 'ZALCPE'
            }
            
            fallback_patterns = [
                (r'CONSTITUTIONAL\s+COURT', 'ZACC'),
                (r'SUPREME\s+COURT\s+OF\s+APPEAL', 'ZASCA'),
                (r'GAUTENG.*JOHANNESBURG', 'ZAGPJHC'),
                (r'GAUTENG.*PRETORIA', 'ZAGPPHC'),
                (r'WESTERN\s+CAPE', 'ZAWCHC'),
                (r'KWAZULU-NATAL.*DURBAN', 'ZAKZDHC'),
                (r'KWAZULU-NATAL.*PIETERMARITZBURG', 'ZAKZPHC'),
                (r'EASTERN\s+CAPE.*GRAHAMSTOWN', 'ZAECGHC'),
                (r'EASTERN\s+CAPE.*PORT\s+ELIZABETH', 'ZAECPEHC'),
                (r'EASTERN\s+CAPE.*MTHATHA', 'ZAECMHC'),
                (r'FREE\s+STATE', 'ZAFSHC'),
                (r'NORTH\s+WEST', 'ZANWHC'),
                (r'LIMPOPO', 'ZALMPPHC'),
                (r'MPUMALANGA', 'ZAMPUMALANGA'),
                (r'NORTHERN\s+CAPE', 'ZANCHC'),
                (r'LABOUR\s+APPEAL\s+COURT', 'ZALAC'),
                (r'LABOUR\s+COURT.*JOHANNESBURG', 'ZALCJHB'),
                (r'LABOUR\s+COURT.*CAPE\s+TOWN', 'ZALCCT'),
                (r'LABOUR\s+COURT.*DURBAN', 'ZALCDBN'),
                (r'LABOUR\s+COURT.*PORT\s+ELIZABETH', 'ZALCPE'),
            ]
            
            return fallback_codes, fallback_patterns
    
    @classmethod
    def get_court_codes(cls) -> Set[str]:
        """Get the set of court codes, loading from YAML if needed."""
        if cls._COURT_CODES is None:
            cls._COURT_CODES, cls._COURT_PATTERNS = cls.load_courts_from_yaml()
        return cls._COURT_CODES
    
    @classmethod
    def get_court_patterns(cls) -> List[Tuple[str, str]]:
        """Get the list of court name patterns, loading from YAML if needed."""
        if cls._COURT_PATTERNS is None:
            cls._COURT_CODES, cls._COURT_PATTERNS = cls.load_courts_from_yaml()
        return cls._COURT_PATTERNS

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
        
        # Extract neutral citation components [YYYY] COURT XX
        neutral_citation_match = re.search(r'\[(\d{4})\]\s+([A-Z]+)\s+(\d+)', self.title)
        if neutral_citation_match:
            year, court_code, number = neutral_citation_match.groups()
            if court_code in self.get_court_codes():  # Only accept valid court codes
                metadata['court'] = court_code
                metadata['full_citation'] = f"[{year}] {court_code} {number}"
                metadata['neutral_citation_year'] = int(year)
                metadata['neutral_citation_number'] = int(number)

        # Extract case number - look for specific patterns
        case_number_patterns = [
            r'\(([A-Z]+\s*\d+/\d+(?:/\d+)?)\)',  # (CCT 209/22) or (A 169/2024)
            r'\((\d+/\d+(?:/\d+)?)\)',           # (12345/2024)
            r'Case\s+No\.?\s*(\d+/\d+(?:/\d+)?)', # Case No. 12345/2024
        ]
        
        for pattern in case_number_patterns:
            match = re.search(pattern, self.title)
            if match:
                metadata['case_number'] = match.group(1).strip()
                break

        # Extract date - look for date at the end of the title
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
        for code in self.get_court_codes():
            if re.search(rf'\b{code}\b', self.first_50_lines):
                return code
        
        # Look for court name in header and map to code
        for pattern, code in self.get_court_patterns():
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
        # Common judicial titles
        judicial_titles = r'(?:Justice|Judge|J\.|JA|AJA|ADJP|DCJ|ACJ|JP|AJP|DCJP)'
        
        # Words that might indicate a judge name but should be ignored
        ignore_words = [
            'court', 'appeal', 'case', 'matter', 'hearing', 'trial', 'judgment',
            'representative', 'representatives', 'email', 'upload', 'uploading',
            'during', 'plea', 'his', 'her', 'their', 'the', 'this', 'that',
            'caselines', 'by', 'for', 'with', 'and', 'or', 'of', 'in', 'on',
            'at', 'to', 'from', 'into', 'onto', 'upon', 'within', 'without'
        ]
        
        # Pattern to match judge names
        pattern = fr'(?:[A-Z][a-zA-Z\'\-]+(?:\s+[A-Z][a-zA-Z\'\-]+)*)\s+{judicial_titles}'
        
        # Find all potential matches
        matches = re.finditer(pattern, self.first_50_lines)
        judges = []
        
        for match in matches:
            name = match.group(0).strip()
            
            # Skip if the name contains any ignore words
            if any(word.lower() in name.lower() for word in ignore_words):
                continue
                
            # Clean up the name
            name = re.sub(r'\s+', ' ', name)  # normalize whitespace
            name = re.sub(r'\s+J\.?$', ' J', name)  # normalize J suffix
            
            # Validate name length (between 3 and 50 characters)
            if 3 <= len(name) <= 50:
                judges.append(name)
        
        # Remove duplicates while preserving order
        seen = set()
        judges = [x for x in judges if not (x in seen or seen.add(x))]
        
        return ', '.join(judges) if judges else None

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
