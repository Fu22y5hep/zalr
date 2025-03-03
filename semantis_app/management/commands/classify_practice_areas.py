#!/usr/bin/env python3
"""
Django management command for classifying practice areas from short summaries.
Uses a hybrid approach:
1. Rule-based check for strong keyword matches
2. Fallback to Zero-Shot Classification with Hugging Face
3. Final fallback to OpenAI GPT (gpt-4o-mini) if zero-shot also fails
"""

import os
import yaml
import re
import logging
from typing import List, Tuple, Optional
import argparse
from django.core.management.base import BaseCommand
from transformers import pipeline
import torch
from openai import OpenAI
from django.conf import settings
from django.db import models

from semantis_app.models import Judgment

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure OpenAI
openai_api_key = os.getenv("OPENAI_API_KEY")

class Command(BaseCommand):
    help = 'Classify practice areas from judgment short summaries'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=20,
                          help='Number of judgments to process (default: 20)')
        parser.add_argument('--force', action='store_true',
                          help='Process all judgments, even those that already have practice areas (by default, only processes judgments with no practice area or marked as "Not Classified")')

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS(f"Starting practice area classification process"))
        self.stdout.write(f"Configuration:")
        self.stdout.write(f"- Batch size: {batch_size}")
        self.stdout.write(f"- Force mode: {'enabled' if force else 'disabled'}")
        
        self.process_all_judgments(batch_size=batch_size, force=force)
        self.stdout.write(self.style.SUCCESS("Practice area classification process completed"))

    # -----------------------------------------------------------------------------
    # 1. Load the Practice Areas Configuration
    # -----------------------------------------------------------------------------

    def load_practice_areas(self, yaml_path: str = None) -> tuple:
        """
        Load the YAML file containing all practice areas and extract keywords.
        Returns a tuple of (practice_areas_list, keywords_map)
        """
        try:
            if yaml_path is None:
                # Use Django's BASE_DIR to construct an absolute path
                from django.conf import settings
                import os
                yaml_path = os.path.join(settings.BASE_DIR, 'semantis_app', 'config', 'practice_areas.yaml')
                
            logger.info(f"Loading practice areas from: {yaml_path}")
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = f.read()
                
            # Extract practice areas and their keywords from the YAML content
            practice_areas = []
            keywords_map = {}
            
            for line in data.split('\n'):
                # Look for lines that start with a number followed by a period and asterisks (practice areas)
                area_match = re.match(r'\d+\.\s+\*\*([^*]+)\*\*', line)
                if area_match:
                    area = area_match.group(1).strip()
                    practice_areas.append(area)
                    keywords_map[area] = []
                
                # Look for lines with descriptions in parentheses (keywords)
                if practice_areas:  # Only if we've already found at least one practice area
                    current_area = practice_areas[-1]
                    # Extract text in parentheses - match both *(text)* and (text) formats
                    keyword_match = re.search(r'\*?\(([^)]+)\)\*?', line)
                    if keyword_match:
                        # Split the description into individual keywords
                        description = keyword_match.group(1).lower()
                        # Extract individual phrases separated by commas
                        keywords = [k.strip() for k in re.split(r',|;', description)]
                        # Add area name words as keywords too
                        area_words = [w.lower() for w in re.split(r'\W+', current_area) if w and len(w) > 2]
                        
                        # Combine all keywords
                        all_keywords = keywords + area_words
                        keywords_map[current_area] = all_keywords
            
            logger.info(f"Found {len(practice_areas)} practice areas")
            for area, keywords in keywords_map.items():
                logger.debug(f"  - {area}: {len(keywords)} keywords")
                
            return practice_areas, keywords_map
            
        except Exception as e:
            logger.error(f"Error loading practice areas: {str(e)}")
            return [], {}

    # -----------------------------------------------------------------------------
    # 2. Build a Rule-Based Dictionary (KEYWORDS_MAP)
    # -----------------------------------------------------------------------------

    def build_keywords_map(self, practice_areas: List[str], keywords_map: dict) -> dict:
        """
        Enhances the keywords map with additional common keywords for each practice area.
        """
        # Additional common keywords for areas that might not be fully covered in the YAML
        additional_keywords = {
            "ADMINISTRATIVE LAW": ["administrative", "judicial review", "public bodies", "administrative fairness", "PAJA", "municipal law"],
            "COMMERCIAL LAW": ["commercial", "contract", "company", "insolvency", "banking", "credit"],
            "COMPETITION LAW": ["competition", "anti-trust", "merger", "acquisition", "cartel", "prohibited practice"],
            "CONSTITUTIONAL LAW": ["constitutional", "bill of rights", "fundamental rights", "equality", "discrimination"],
            "CRIMINAL LAW": ["criminal", "offence", "sentence", "bail", "evidence", "arrest", "prosecution"],
            "DELICTUAL LAW": ["delict", "negligence", "liability", "injury", "damages", "defamation", "wrongful", "road accident fund", "PRASA", "Medical negligence"],
            "ENVIRONMENTAL LAW": ["environmental", "conservation", "pollution", "impact assessment", "land use"],
            "FAMILY LAW": ["family", "divorce", "custody", "matrimonial", "maintenance", "domestic violence", "succession"],
            "INSURANCE LAW": ["insurance", "policy", "claim", "short-term", "long-term", "regulatory"],
            "INTELLECTUAL PROPERTY LAW": ["intellectual property", "copyright", "patent", "trademark", "design", "passing-off", "domain name"],
            "LABOUR LAW": ["labour", "employment", "dismissal", "strike", "collective bargaining", "unfair labour practice"],
            "LAND AND PROPERTY LAW": ["property", "land", "servitude", "expropriation", "sectional title", "landlord", "tenant"],
            "PRACTICE AND PROCEDURE": ["procedure", "evidence", "discovery", "condonation", "interlocutory", "practice directive"],
            "TAX LAW": ["tax", "income tax", "VAT", "customs", "excise", "transfer pricing"],
            "ARBITRATION": ["arbitration", "arbitral", "arbitration agreement", "arbitration proceeding", "arbitral award"],
        }

        # Enhance the keywords map with additional keywords
        for area in practice_areas:
            if area in additional_keywords:
                # Add any additional keywords not already in the list
                existing_keywords = set(keywords_map.get(area, []))
                for keyword in additional_keywords[area]:
                    if keyword.lower() not in existing_keywords:
                        keywords_map.setdefault(area, []).append(keyword.lower())

        return keywords_map

    # -----------------------------------------------------------------------------
    # 3. Rule-Based Classifier
    # -----------------------------------------------------------------------------

    def rule_based_classify(self, text: str, keywords_map: dict, threshold: int = 2) -> List[Tuple[str, int]]:
        """
        Returns a list of (practice_area, match_score) sorted by descending match_score.
        """
        text_lower = text.lower()
        results = []

        for area, kw_list in keywords_map.items():
            score = 0
            for kw in kw_list:
                if kw in text_lower:
                    score += text_lower.count(kw)
            results.append((area, score))
        
        # Sort by descending order
        results.sort(key=lambda x: x[1], reverse=True)

        # Filter out areas that have no matches
        filtered_results = [(area, sc) for (area, sc) in results if sc > 0]

        return filtered_results

    # -----------------------------------------------------------------------------
    # 4. Zero-Shot Fallback Classifier
    # -----------------------------------------------------------------------------

    # Initialize the classifier once
    _classifier = None

    def get_classifier(self):
        """
        Singleton pattern to initialize the classifier only once.
        """
        if not hasattr(self, '_classifier') or self._classifier is None:
            device = 0 if torch.cuda.is_available() else -1
            self._classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=device,
                framework="pt"  # Explicitly use PyTorch
            )
        return self._classifier

    def zero_shot_classify(self, text: str, candidate_labels: List[str]) -> Optional[str]:
        """
        Uses a Hugging Face zero-shot classification pipeline to pick the best practice area.
        """
        try:
            if not candidate_labels:
                logger.error("No candidate labels provided for classification")
                return None

            classifier = self.get_classifier()
            
            # Log the candidate labels for debugging
            logger.debug(f"Classifying with labels: {candidate_labels}")
            
            # Create a more specific hypothesis template for legal domain classification
            hypothesis_template = "This legal case involves matters of {}."
            
            results = classifier(
                sequences=text,
                candidate_labels=candidate_labels,
                multi_label=False,
                hypothesis_template=hypothesis_template
            )
            
            # Log the classification scores for debugging
            for label, score in zip(results["labels"], results["scores"]):
                logger.debug(f"Label: {label}, Score: {score}")
            
            best_label = results["labels"][0]
            best_score = results["scores"][0]
            second_best_score = results["scores"][1] if len(results["scores"]) > 1 else 0
            
            # Return the label if:
            # 1. Score is above 0.3 (lowered from 0.5)
            # 2. OR score is above 0.2 and significantly higher than second best
            if best_score > 0.3 or (best_score > 0.2 and best_score > second_best_score * 1.5):
                return best_label
            return None
            
        except Exception as e:
            logger.error(f"Error in zero-shot classification: {str(e)}")
            return None

    # -----------------------------------------------------------------------------
    # 5. OpenAI GPT Fallback Classifier
    # -----------------------------------------------------------------------------

    def openai_fallback_classify(self, text: str, candidate_labels: List[str]) -> Optional[str]:
        """
        Uses OpenAI GPT as a final fallback classifier.
        """
        try:
            # Construct a prompt for GPT classification
            system_instructions = (
                "You are an AI assistant specialized in South African legal case classification. "
                "Your goal is to pick exactly ONE domain from the provided list of candidate labels, "
                "based on which domain best fits the text. "
                "If you must guess, do so with the best logical reasoning. "
                "Respond ONLY with the chosen label, nothing else."
            )
            user_prompt = (
                f"Text to classify:\n'''{text}'''\n\n"
                f"Candidate labels: {', '.join(candidate_labels)}\n"
                "Which single label best describes this text?"
            )

            # Check if API key is available
            if not openai_api_key:
                logger.error("OpenAI API key is not set in environment variables")
                return None

            # Initialize the OpenAI client
            client = OpenAI(api_key=openai_api_key)
            
            # Make the API call using the new client syntax
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=128
            )
            
            # Extract the content from the response
            gpt_output = response.choices[0].message.content.strip()
            
            # Match the output against candidate labels
            best_label = None
            for label in candidate_labels:
                if label.lower() in gpt_output.lower():
                    best_label = label
                    break
            
            logger.info(f"OpenAI GPT classification: {best_label or 'None'}")
            return best_label

        except Exception as e:
            logger.error(f"OpenAI GPT fallback error: {str(e)}")
            # If we get an API error, log more details to help with debugging
            if hasattr(e, 'response'):
                logger.error(f"API Response: {e.response}")
            return None

    # -----------------------------------------------------------------------------
    # 6. Orchestration: Hybrid Classification Approach
    # -----------------------------------------------------------------------------

    def classify_practice_area(self, text: str, practice_areas: List[str], keywords_map: dict, rule_threshold: int = 2) -> str:
        """
        1. Attempt rule-based classification.
        2. If inconclusive or multiple high scorers, fall back to zero-shot.
        3. If zero-shot fails, try OpenAI GPT.
        4. Return the best single practice area.
        """
        if not text:
            logger.warning("Empty text provided for classification")
            return "Not Classified"

        # 1. Rule-based pass
        rb_results = self.rule_based_classify(text, keywords_map, threshold=rule_threshold)

        if not rb_results:
            logger.info("Rule-based found no strong matches; falling back to zero-shot.")
            # Try zero-shot classification
            zero_shot_result = self.zero_shot_classify(text, practice_areas)
            if not zero_shot_result:
                logger.info("Zero-shot classification failed; falling back to OpenAI GPT.")
                # Try OpenAI GPT
                openai_result = self.openai_fallback_classify(text, practice_areas)
                if openai_result:
                    return openai_result
                else:
                    logger.info("OpenAI GPT failed; using simple keyword matching as final fallback.")
                    # Simple keyword matching as final fallback
                    return self.simple_keyword_fallback(text, practice_areas) or "Not Classified"
            return zero_shot_result

        # If there's a clear winner
        if len(rb_results) == 1:
            area, score = rb_results[0]
            if score >= rule_threshold:
                return area
            else:
                logger.info("Top area score below threshold; using zero-shot fallback.")
                zero_shot_result = self.zero_shot_classify(text, practice_areas)
                if not zero_shot_result:
                    logger.info("Zero-shot classification failed; falling back to OpenAI GPT.")
                    openai_result = self.openai_fallback_classify(text, practice_areas)
                    if openai_result:
                        return openai_result
                    else:
                        logger.info("OpenAI GPT failed; using simple keyword matching as final fallback.")
                        return self.simple_keyword_fallback(text, practice_areas) or "Not Classified"
                return zero_shot_result

        # If multiple results
        top_area, top_score = rb_results[0]
        second_area, second_score = rb_results[1] if len(rb_results) > 1 else ("", 0)

        # If top area's score is well above second area, pick top
        if top_score > second_score + 2:  # margin of 2
            return top_area
        else:
            logger.info("Multiple areas have similar scores; using zero-shot fallback.")
            zero_shot_result = self.zero_shot_classify(text, practice_areas)
            if not zero_shot_result:
                logger.info("Zero-shot classification failed; falling back to OpenAI GPT.")
                openai_result = self.openai_fallback_classify(text, practice_areas)
                if openai_result:
                    return openai_result
                else:
                    logger.info("OpenAI GPT failed; using simple keyword matching as final fallback.")
                    return self.simple_keyword_fallback(text, practice_areas) or "Not Classified"
            return zero_shot_result
            
    def simple_keyword_fallback(self, text: str, practice_areas: List[str]) -> Optional[str]:
        """
        A very simple keyword-based classifier as a last resort.
        Just checks for exact matches of practice area names in the text.
        """
        text_lower = text.lower()
        
        # First try exact matches of practice area names
        for area in practice_areas:
            if area.lower() in text_lower:
                return area
                
        # If no exact matches, try partial matches
        for area in practice_areas:
            # Split the area name into words
            words = [w.lower() for w in re.split(r'\W+', area) if w and len(w) > 3]
            # Count how many words match
            matches = sum(1 for word in words if word in text_lower)
            # If more than half the words match, return this area
            if matches > 0 and matches >= len(words) / 2:
                return area
                
        return None

    # -----------------------------------------------------------------------------
    # 7. Database Operations
    # -----------------------------------------------------------------------------

    def process_judgment(self, judgment: Judgment, practice_areas: List[str], keywords_map: dict) -> bool:
        """Process a single judgment to extract and save its practice area."""
        try:
            logger.info(f"Processing judgment: {judgment.title}")
            
            if not judgment.short_summary:
                logger.warning(f"No short summary found for judgment: {judgment.title}")
                return False
                
            practice_area = self.classify_practice_area(judgment.short_summary, practice_areas, keywords_map)
            if practice_area and practice_area != "Not Classified":
                judgment.practice_area = practice_area
                judgment.save()
                logger.info(f"Successfully classified {judgment.title} as {practice_area}")
                return True
            else:
                # Save "Not Classified" as the practice area instead of leaving it null
                judgment.practice_area = "Not Classified"
                judgment.save()
                logger.warning(f"Could not classify {judgment.title}, marked as 'Not Classified'")
                return False
            
        except Exception as e:
            logger.error(f"Error processing judgment {judgment.title}: {str(e)}")
            return False

    def process_all_judgments(self, batch_size: int = 20, force: bool = False):
        """Process all judgments in batches."""
        try:
            # Load practice areas
            practice_areas, keywords_map = self.load_practice_areas()
            if not practice_areas:
                logger.error("Failed to load practice areas")
                return

            # Build keywords map
            keywords_map = self.build_keywords_map(practice_areas, keywords_map)
            
            # Get total count of judgments that need processing
            query = Judgment.objects.filter(short_summary__isnull=False)
            if not force:
                # Process judgments that have no practice area or are marked as "Not Classified"
                query = query.filter(models.Q(practice_area__isnull=True) | models.Q(practice_area="Not Classified"))
                
            total_judgments = query.count()
            
            if total_judgments == 0:
                logger.info("No judgments found that need processing")
                return
                
            logger.info(f"Found {total_judgments} judgments that need processing")
            logger.info(f"Processing batch of {batch_size} judgments")
            logger.info(f"Force mode: {'enabled' if force else 'disabled'}")
            
            # Get judgments to process
            judgments = query.order_by('judgment_date')[:batch_size]
            
            total = len(judgments)
            successful = failed = 0
            
            for i, judgment in enumerate(judgments, 1):
                logger.info(f"Processing judgment {i} of {total} (Total remaining: {total_judgments - i})")
                if self.process_judgment(judgment, practice_areas, keywords_map):
                    successful += 1
                else:
                    failed += 1
                    
            logger.info(f"Processing completed. Successful: {successful}, Failed: {failed}")
            logger.info(f"Remaining judgments to process: {total_judgments - successful}")
            
        except Exception as e:
            logger.error(f"Error in process_all_judgments: {str(e)}") 