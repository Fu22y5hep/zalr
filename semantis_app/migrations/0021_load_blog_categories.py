# Generated by Django 5.1.6 on 2025-03-03 19:44

from django.db import migrations
import yaml
import os

def load_blog_categories(apps, schema_editor):
    BlogCategory = apps.get_model('semantis_app', 'BlogCategory')
    
    # Get the path to the YAML file
    yaml_path = os.path.join(os.path.dirname(__file__), '..', 'blog_categories.yaml')
    
    # Read the YAML file
    with open(yaml_path, 'r') as file:
        data = yaml.safe_load(file)
    
    # Create categories
    for category_data in data['categories']:
        BlogCategory.objects.create(
            name=category_data['name'],
            slug=category_data['slug'],
            description=category_data['description']
        )

def reverse_load_blog_categories(apps, schema_editor):
    BlogCategory = apps.get_model('semantis_app', 'BlogCategory')
    BlogCategory.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('semantis_app', '0020_blogcomment'),
    ]

    operations = [
        migrations.RunPython(load_blog_categories, reverse_load_blog_categories),
    ]
