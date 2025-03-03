from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for the blog API
router = DefaultRouter()
router.register(r'blog/categories', views.BlogCategoryViewSet)
router.register(r'blog/posts', views.BlogPostViewSet)
router.register(r'blog/comments', views.BlogCommentViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 