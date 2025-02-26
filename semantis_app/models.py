from django.db import models
from pgvector.django import VectorField
import uuid

class Judgment(models.Model):
    """
    Model to store legal judgments with their metadata, vector embeddings and text chunks
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=1000)
    full_citation = models.TextField(null=True, blank=True)
    neutral_citation_year = models.IntegerField(null=True, blank=True)  # e.g., 2024 from [2024] ZACC 1
    court = models.TextField(max_length=8, null=True, blank=True)
    neutral_citation_number = models.IntegerField(null=True, blank=True)
    judgment_date = models.DateField(null=True, blank=True)
    judges = models.TextField(null=True, blank=True)
    text_markdown = models.TextField()
    vector_embedding = VectorField(dimensions=1024, null=True, blank=True)  # Using 1024 dimensions for voyage-law-2
    reportability_score = models.IntegerField(default=0)
    reportability_explanation = models.TextField(null=True, blank=True)  # Store the full explanation from GPT
    short_summary = models.TextField(null=True, blank=True)
    long_summary = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    chunks = models.JSONField(null=True, blank=True)
    chunks_embedded = models.BooleanField(default=False)
    case_number = models.CharField(max_length=25, null=True, blank=True)
    saflii_url = models.URLField(max_length=200, null=True, blank=True)# Track if chunks have been embedded
    featured = models.BooleanField(default=False)  # Track if this is the featured judgment of the week

    def __str__(self):
        return f"{self.title} ({self.case_number})"

    class Meta:
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['case_number']),
            models.Index(fields=['judgment_date']),
        ]

class Statute(models.Model):
    """
    Model to store statutes and their vector embeddings
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    act_number = models.CharField(max_length=50, null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    text_markdown = models.TextField()
    vector_embedding = VectorField(dimensions=1024, null=True, blank=True)
    source_url = models.URLField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} (Act {self.act_number} of {self.year})"

    class Meta:
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['year']),
            models.Index(fields=['act_number']),
        ]

class SearchHistory(models.Model):
    """
    Model to store user search history
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=255, null=True, blank=True)  # Supabase user ID
    query = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Search by {self.user_id}: {self.query[:50]}..."

    class Meta:
        indexes = [
            models.Index(fields=['user_id']),
            models.Index(fields=['timestamp']),
        ]
        verbose_name_plural = "Search histories"

class SavedCase(models.Model):
    """
    Model to store cases saved by users
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=255)  # Supabase user ID
    case = models.ForeignKey(Judgment, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} saved {self.case.title}"

    class Meta:
        indexes = [
            models.Index(fields=['user_id']),
            models.Index(fields=['timestamp']),
        ]
        unique_together = ['user_id', 'case']  # Prevent duplicate saves

class ScoringSection(models.Model):
    """
    Model to store individual scoring sections for judgments
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    judgment = models.ForeignKey(Judgment, on_delete=models.CASCADE, related_name='scoring_sections')
    section_name = models.CharField(max_length=255)
    score = models.IntegerField()
    explanation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.section_name} - Score: {self.score}"

    class Meta:
        indexes = [
            models.Index(fields=['judgment']),
            models.Index(fields=['section_name']),
        ]

class ScoreValidation(models.Model):
    """
    Model to store validation results for LLM scoring
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    judgment = models.ForeignKey(Judgment, on_delete=models.CASCADE, related_name='score_validations')
    validation_passed = models.BooleanField(default=False)
    validation_message = models.TextField(null=True, blank=True)
    validated_at = models.DateTimeField(auto_now_add=True)
    validated_by = models.CharField(max_length=255, null=True, blank=True)  # Could be LLM model name or human validator

    def __str__(self):
        return f"Validation for {self.judgment.title} - {'Passed' if self.validation_passed else 'Failed'}"

    class Meta:
        indexes = [
            models.Index(fields=['judgment']),
            models.Index(fields=['validation_passed']),
            models.Index(fields=['validated_at']),
        ]
