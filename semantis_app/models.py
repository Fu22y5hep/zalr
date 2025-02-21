from django.db import models
from pgvector.django import VectorField
import uuid

class Judgment(models.Model):
    """
    Model to store legal judgments with their metadata and vector embeddings
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=1000)
    full_citation = models.TextField(null=True, blank=True)
    court = models.CharField(max_length=255, null=True, blank=True)
    case_number = models.CharField(max_length=100, null=True, blank=True)
    judgment_date = models.DateField(null=True, blank=True)
    judges = models.TextField(null=True, blank=True)
    text_markdown = models.TextField()
    vector_embedding = VectorField(dimensions=768, null=True, blank=True)  # Using 768 dimensions for compatibility with many embedding models
    saflii_url = models.URLField(max_length=200, null=True, blank=True)
    reportability_score = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

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
    vector_embedding = VectorField(dimensions=768, null=True, blank=True)
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
