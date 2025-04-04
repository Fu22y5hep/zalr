from django.shortcuts import render
from rest_framework import viewsets, status, generics, permissions
from rest_framework.response import Response
from rest_framework.decorators import action, api_view
from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings
import openai
from openai import OpenAI
import logging
import json
import uuid
import os

from .models import BlogPost, BlogCategory, BlogComment, Judgment
from .serializers import (
    BlogPostListSerializer, 
    BlogPostDetailSerializer, 
    BlogPostCreateSerializer,
    BlogCategorySerializer,
    BlogCommentSerializer
)

# Set up logging
logger = logging.getLogger(__name__)

# Create your views here.

@api_view(['GET'])
def search_by_citation(request):
    """
    API endpoint to search judgments by citation number
    """
    citation_number = request.query_params.get('citation_number')
    if not citation_number:
        return Response(
            {"detail": "Citation number is required"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Try to convert the citation number to an integer
        citation_int = int(citation_number)
        
        # Get the court code and year if provided
        court = request.query_params.get('court')
        year = request.query_params.get('year')
        
        # Build the query
        query = {'neutral_citation_number': citation_int}
        
        if court:
            query['court'] = court
            
        if year:
            try:
                year_int = int(year)
                query['neutral_citation_year'] = year_int
            except ValueError:
                # If year is not a valid integer, ignore it
                pass
                
        # Try to find the judgment
        judgment = Judgment.objects.filter(**query).first()
        
        if judgment:
            # Return basic judgment information
            result = {
                'id': judgment.id,
                'title': judgment.title,
                'court': judgment.court,
                'citation': f"[{judgment.neutral_citation_year}] {judgment.court} {judgment.neutral_citation_number}",
                'judgment_date': judgment.judgment_date.isoformat() if judgment.judgment_date else None,
                'judges': judgment.judges,
                'case_number': judgment.case_number,
                'short_summary': judgment.short_summary,
            }
            return Response(result)
        else:
            return Response(
                {"detail": "No judgment found with the specified citation number"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    except ValueError:
        return Response(
            {"detail": "Citation number must be a valid integer"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error searching for judgment by citation: {str(e)}")
        return Response(
            {"detail": f"An error occurred: {str(e)}"}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class BlogCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for blog categories
    """
    queryset = BlogCategory.objects.all()
    serializer_class = BlogCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = 'slug'


class BlogPostViewSet(viewsets.ModelViewSet):
    """
    API endpoint for blog posts with DALL-E image generation
    """
    queryset = BlogPost.objects.all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = 'slug'
    
    def get_serializer_class(self):
        if self.action == 'list':
            return BlogPostListSerializer
        elif self.action == 'create':
            return BlogPostCreateSerializer
        return BlogPostDetailSerializer
    
    def get_queryset(self):
        queryset = BlogPost.objects.all()
        # Only show published posts to non-staff users
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_published=True)
        return queryset
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get the image generation prompt if provided
        image_prompt = request.data.get('image_generation_prompt')
        image_url = None
        
        # Generate image with DALL-E if a prompt is provided
        if image_prompt:
            try:
                image_url = self.generate_image_with_dalle(image_prompt)
                
                # Save the prompt and URL
                serializer.validated_data['image_prompt'] = image_prompt
                serializer.validated_data['image_url'] = image_url
                
            except Exception as e:
                logger.error(f"Error generating image with DALL-E: {str(e)}")
                # Continue without image if generation fails
                pass
        
        # Create the blog post
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def generate_image_with_dalle(self, prompt):
        """
        Generate an image using DALL-E based on the provided prompt
        """
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Generate image with DALL-E
            response = client.images.generate(
                model="dall-e-3",  # or dall-e-2 for a smaller, cheaper alternative
                prompt=prompt,
                size="1024x1024",  # Standard size
                quality="standard",
                n=1,
            )
            
            # Return the URL of the generated image
            return response.data[0].url
            
        except Exception as e:
            logger.error(f"DALL-E image generation failed: {str(e)}")
            raise
    
    def perform_create(self, serializer):
        # Set publication date if post is being published
        if serializer.validated_data.get('is_published', False):
            serializer.validated_data['published_at'] = timezone.now()
        
        serializer.save()


class BlogCommentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for blog comments
    """
    queryset = BlogComment.objects.all()
    serializer_class = BlogCommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        queryset = BlogComment.objects.all()
        
        # Filter by post slug if provided
        post_slug = self.request.query_params.get('post_slug', None)
        if post_slug:
            queryset = queryset.filter(post__slug=post_slug)
        
        # Filter by approval status
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_approved=True)
            
        return queryset
    
    def create(self, request, *args, **kwargs):
        # Add the Supabase user ID from the request
        supabase_user_id = self.request.META.get('HTTP_SUPABASE_USER_ID')
        if not supabase_user_id:
            return Response(
                {"detail": "Authentication required. Supabase user ID not provided."}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Add user ID to request data
        mutable_data = request.data.copy()
        mutable_data['supabase_user_id'] = supabase_user_id
        
        serializer = self.get_serializer(data=mutable_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
