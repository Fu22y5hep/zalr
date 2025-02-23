from typing import List, Dict, Tuple
from ..models import Judgment, ScoringSection, ScoreValidation

class ScoreValidator:
    """
    Utility class to validate LLM-generated scores for judgments
    """
    
    @staticmethod
    def validate_section_scores(judgment: Judgment) -> Tuple[bool, str]:
        """
        Validates the scores for all sections of a judgment
        
        Args:
            judgment: The Judgment instance to validate
            
        Returns:
            Tuple of (validation_passed: bool, validation_message: str)
        """
        sections = judgment.scoring_sections.all()
        
        # Basic validation checks
        validation_checks = [
            ScoreValidator._check_section_completeness(sections),
            ScoreValidator._check_score_ranges(sections),
            ScoreValidator._check_total_score(judgment, sections),
        ]
        
        # Combine all validation results
        all_passed = all(result[0] for result in validation_checks)
        messages = [msg for _, msg in validation_checks if msg]
        
        # Create validation record
        ScoreValidation.objects.create(
            judgment=judgment,
            validation_passed=all_passed,
            validation_message="\n".join(messages) if messages else "All validations passed",
            validated_by="ScoreValidator"
        )
        
        return all_passed, "\n".join(messages) if messages else "All validations passed"
    
    @staticmethod
    def _check_section_completeness(sections: List[ScoringSection]) -> Tuple[bool, str]:
        """Checks if all required sections are present"""
        required_sections = {
            'legal_principle',
            'factual_complexity',
            'judicial_analysis',
            'precedential_value',
            'public_importance'
        }
        
        existing_sections = {section.section_name for section in sections}
        missing_sections = required_sections - existing_sections
        
        if missing_sections:
            return False, f"Missing required sections: {', '.join(missing_sections)}"
        return True, ""
    
    @staticmethod
    def _check_score_ranges(sections: List[ScoringSection]) -> Tuple[bool, str]:
        """Validates that all scores are within acceptable ranges (0-20)"""
        invalid_scores = []
        for section in sections:
            if not 0 <= section.score <= 20:
                invalid_scores.append(f"{section.section_name}: {section.score}")
        
        if invalid_scores:
            return False, f"Invalid scores found (must be 0-20): {', '.join(invalid_scores)}"
        return True, ""
    
    @staticmethod
    def _check_total_score(judgment: Judgment, sections: List[ScoringSection]) -> Tuple[bool, str]:
        """Validates that the total score matches the sum of section scores"""
        total_section_score = sum(section.score for section in sections)
        
        if total_section_score != judgment.reportability_score:
            return False, f"Total score mismatch: sections sum to {total_section_score} but judgment score is {judgment.reportability_score}"
        return True, "" 