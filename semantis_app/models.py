from django.db import models
from pgvector.django import VectorField
import uuid
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

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
    reportability_score = models.IntegerField(null=True, blank=True)
    reportability_explanation = models.TextField(null=True, blank=True)  # Store the full explanation from GPT
    short_summary = models.TextField(null=True, blank=True)
    long_summary = models.TextField(null=True, blank=True)
    practice_areas = models.TextField(null=True, blank=True)  # Store comma-separated practice areas
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
    Model to store legal statutes with their metadata and vector embeddings
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=1000)
    act_number = models.CharField(max_length=25, null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    text_markdown = models.TextField()
    vector_embedding = VectorField(dimensions=1024, null=True, blank=True)  # Using 1024 dimensions for voyage-law-2
    source_url = models.URLField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    chunks = models.JSONField(null=True, blank=True)
    chunks_embedded = models.BooleanField(default=False)  # Track if chunks have been embedded

    def __str__(self):
        return f"{self.title} (Act No. {self.act_number} of {self.year})"

    class Meta:
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['act_number']),
            models.Index(fields=['year']),
        ]

class SearchHistory(models.Model):
    """
    Model to store user search history
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supabase_user_id = models.CharField(max_length=255, null=True, blank=True)  # Supabase user ID
    query = models.TextField()
    case = models.ForeignKey(Judgment, on_delete=models.CASCADE, null=True, blank=True, db_column='research_judgment_id')
    ai_response = models.TextField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user = self.supabase_user_id or "Anonymous"
        return f"Search by {user}: {self.query[:50]}..."

    class Meta:
        indexes = [
            models.Index(fields=['supabase_user_id']),
            models.Index(fields=['timestamp']),
        ]
        verbose_name_plural = "Search histories"

class SavedCase(models.Model):
    """
    Model to store cases saved by users
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supabase_user_id = models.CharField(max_length=255)  # Supabase user ID
    case = models.ForeignKey(Judgment, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.supabase_user_id} saved {self.case.title}"

    class Meta:
        indexes = [
            models.Index(fields=['supabase_user_id']),
            models.Index(fields=['timestamp']),
        ]
        unique_together = ['supabase_user_id', 'case']  # Prevent duplicate saves

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

class UserProfile(models.Model):
    """
    Extension of the Django User model to include Supabase user_id
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    supabase_user_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s profile (Supabase ID: {self.supabase_user_id})"

# Signal to create a UserProfile when a User is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a User is created"""
    if created:
        # Note: supabase_user_id will need to be set manually after creation
        UserProfile.objects.create(user=instance, supabase_user_id="pending")

# Blog Models

class BlogCategory(models.Model):
    """
    Model to store blog categories
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Blog categories"
        ordering = ['name']


class BlogPost(models.Model):
    """
    Model to store blog posts with DALL-E generated images
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    content = models.TextField()
    content_format = models.CharField(max_length=10, default='html', choices=[('html', 'HTML'), ('xml', 'XML')], help_text='Format of the content: html or xml')
    summary = models.TextField(null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    image_prompt = models.TextField(null=True, blank=True)  # Store the prompt used to generate the image
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, related_name='posts')
    author = models.CharField(max_length=100, default="Admin")  # Simple author field, can be expanded
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_published']),
        ]


class BlogComment(models.Model):
    """
    Model to store comments on blog posts
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
    supabase_user_id = models.CharField(max_length=255)  # Supabase user ID
    content = models.TextField()
    is_approved = models.BooleanField(default=True)  # Auto-approve comments initially
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Comment by {self.supabase_user_id[:8]}... on {self.post.title}"
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['supabase_user_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_approved']),
        ]
