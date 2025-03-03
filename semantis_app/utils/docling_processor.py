"""
Docling Integration Utility

This module provides integration with the Docling document processing library.
It handles converting HTML content to Docling Document objects and extracting metadata.

Important Notes:
- Docling's API requires importing:
  - DoclingDocument from docling.datamodel.document
  - DocumentConverter from docling.document_converter
- Every DoclingDocument must have a 'name' attribute set
- The DocumentConverter.convert() method returns a result object that contains the document
"""

import os
import logging
from typing import Dict, Optional, List, Any
import tempfile
from docling.datamodel.document import DoclingDocument
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat

logger = logging.getLogger(__name__)

class DoclingProcessor:
    """Utility class for processing documents using Docling"""
    
    @staticmethod
    def convert_html_to_docling(html_content: str, document_name: str) -> Optional[DoclingDocument]:
        """
        Convert HTML content to Docling Document
        
        Args:
            html_content: The HTML content of the judgment
            document_name: Name to identify the document (required by Docling)
            
        Returns:
            DoclingDocument object or None if conversion fails
        """
        try:
            # Create a temporary HTML file with a proper name
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(html_content)
            
            # Convert using Docling DocumentConverter
            # Format is determined automatically from file extension
            converter = DocumentConverter()
            
            # The convert method accepts a path but doesn't take a format parameter directly
            result = converter.convert(temp_path)
            
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
            if result and result.document:
                # Create a DoclingDocument with the required name
                doc = result.document
                # Set name if not already set
                if not hasattr(doc, 'name') or not doc.name:
                    doc.name = document_name
                return doc
            else:
                logger.error(f"Docling conversion failed: {result.errors if result else 'No result'}")
                return None
        except Exception as e:
            logger.error(f"Error converting to Docling Document: {str(e)}")
            # Clean up in case of error
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass
            return None
    
    @staticmethod
    def get_document_text(doc: DoclingDocument) -> str:
        """
        Extract full text from a DoclingDocument
        
        Args:
            doc: The DoclingDocument object
            
        Returns:
            Full text of the document
        """
        # In the new Docling API, text is accessed through the 'texts' attribute
        # which could be a list of text items or sections
        if hasattr(doc, 'texts') and doc.texts:
            # Join all text items
            if isinstance(doc.texts, list):
                return "\n".join([t.text if hasattr(t, 'text') else str(t) for t in doc.texts])
            # If it's a single item
            elif hasattr(doc.texts, 'text'):
                return doc.texts.text
            # If it's a string
            elif isinstance(doc.texts, str):
                return doc.texts
            # Any other case
            else:
                return str(doc.texts)
        # Fall back to traditional attribute
        elif hasattr(doc, 'text'):
            return doc.text
        # Last resort
        else:
            return str(doc)
    
    @staticmethod
    def extract_metadata(doc: DoclingDocument) -> Dict[str, Any]:
        """
        Extract metadata from a Docling Document
        
        Args:
            doc: The Docling Document object
            
        Returns:
            Dictionary of extracted metadata
        """
        metadata = {}
        
        try:
            # Extract basic metadata from document structure
            # Case name often appears in the title or first heading
            if hasattr(doc, 'metadata') and doc.metadata and 'title' in doc.metadata:
                metadata["case_name"] = doc.metadata['title']
            
            # Get full text from document using our helper method
            full_text = DoclingProcessor.get_document_text(doc)
            
            # Look for citation patterns
            import re
            citation_pattern = r'\[\d{4}\]\s+\w+\s+\d+'
            citation_match = re.search(citation_pattern, full_text)
            if citation_match:
                metadata["full_citation"] = citation_match.group(0)
                
                # Extract court code and year
                court_pattern = r'\[\d{4}\]\s+(\w+)\s+\d+'
                court_match = re.search(court_pattern, metadata["full_citation"])
                if court_match:
                    metadata["court"] = court_match.group(1)
                
                # Extract year
                year_pattern = r'\[(\d{4})\]'
                year_match = re.search(year_pattern, metadata["full_citation"])
                if year_match:
                    metadata["neutral_citation_year"] = int(year_match.group(1))
                
                # Extract number
                number_pattern = r'\[\d{4}\]\s+\w+\s+(\d+)'
                number_match = re.search(number_pattern, metadata["full_citation"])
                if number_match:
                    metadata["neutral_citation_number"] = int(number_match.group(1))
            
            # Extract case number patterns
            case_number_pattern = r'Case No:?\s*(\w+[\w\d\/]+)'
            case_number_match = re.search(case_number_pattern, full_text)
            if case_number_match:
                metadata["case_number"] = case_number_match.group(1).strip()
            
            # Extract judgment date
            date_pattern = r'Date:?\s*(\d{1,2}\s+\w+\s+\d{4})'
            date_match = re.search(date_pattern, full_text)
            if date_match:
                metadata["judgment_date"] = date_match.group(1).strip()
            
            # Extract judges
            judges_pattern = r'(?:Judge|JUDGE|Judges):?\s*([^\.]+)'
            judges_match = re.search(judges_pattern, full_text)
            if judges_match:
                metadata["judges"] = judges_match.group(1).strip()
            
            return metadata
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return metadata 