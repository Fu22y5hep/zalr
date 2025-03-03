from django.contrib import admin
from .models import Judgment, Statute, SearchHistory, SavedCase, ScoringSection, ScoreValidation, UserProfile, BlogPost, BlogCategory, BlogComment

# Register your models here.
admin.site.register(Judgment)
admin.site.register(Statute)
admin.site.register(SearchHistory)
admin.site.register(SavedCase)
admin.site.register(ScoringSection)
admin.site.register(ScoreValidation)
admin.site.register(UserProfile)

# Register Blog models with customized admin interfaces
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'category', 'author', 'is_published', 'created_at')
    list_filter = ('is_published', 'category', 'created_at')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created_at'

class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'supabase_user_id', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'created_at')
    search_fields = ('content', 'supabase_user_id')

admin.site.register(BlogCategory, BlogCategoryAdmin)
admin.site.register(BlogPost, BlogPostAdmin)
admin.site.register(BlogComment, BlogCommentAdmin)
