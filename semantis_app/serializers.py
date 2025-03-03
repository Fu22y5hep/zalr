from rest_framework import serializers
from .models import BlogPost, BlogCategory, BlogComment

class BlogCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogCategory
        fields = ['id', 'name', 'slug', 'description', 'created_at']


class BlogCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogComment
        fields = ['id', 'post', 'supabase_user_id', 'content', 'is_approved', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class BlogPostListSerializer(serializers.ModelSerializer):
    category = BlogCategorySerializer(read_only=True)
    comments_count = serializers.IntegerField(source='comments.count', read_only=True)
    
    class Meta:
        model = BlogPost
        fields = ['id', 'title', 'slug', 'summary', 'image_url', 'category', 'author', 
                 'is_published', 'published_at', 'created_at', 'updated_at', 'comments_count']


class BlogPostDetailSerializer(serializers.ModelSerializer):
    category = BlogCategorySerializer(read_only=True)
    comments = BlogCommentSerializer(many=True, read_only=True)
    
    class Meta:
        model = BlogPost
        fields = ['id', 'title', 'slug', 'content', 'summary', 'image_url', 'image_prompt',
                 'category', 'author', 'is_published', 'published_at', 
                 'created_at', 'updated_at', 'comments']


class BlogPostCreateSerializer(serializers.ModelSerializer):
    image_generation_prompt = serializers.CharField(write_only=True, required=False, 
                                                  help_text="Prompt for DALL-E to generate an image")
    
    class Meta:
        model = BlogPost
        fields = ['title', 'content', 'summary', 'category', 'author', 'is_published', 
                 'image_generation_prompt']
        
    def create(self, validated_data):
        # Remove image_generation_prompt from validated_data before creating the BlogPost
        image_prompt = validated_data.pop('image_generation_prompt', None)
        # The actual image generation will be handled in the view
        
        # Generate a slug from the title
        from django.utils.text import slugify
        validated_data['slug'] = slugify(validated_data['title'])
        
        return super().create(validated_data) 