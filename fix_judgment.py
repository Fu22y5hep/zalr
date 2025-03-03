import os
import django
import sys

# Set up Django environment
sys.path.append('.')  # Add the current directory to path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalr_backend.settings')
django.setup()

# Import required models after Django setup
from semantis_app.models import Judgment
from semantis_app.utils.metadata import MetadataParser

# Get judgment by ID
judgment_id = '44b6025a-d8bc-40d0-9fe6-8344d2740714'
judgment = Judgment.objects.get(id=judgment_id)

# Print current state
print(f"Judgment: {judgment.title}")
print(f"Current court: {judgment.court}")

# Extract metadata from title
parser = MetadataParser(judgment.text_markdown, judgment.title)
title_metadata = parser.parse_title()

print("\nMetadata extracted from title:")
for key, value in title_metadata.items():
    print(f"{key}: {value}")

# Update the court field
if 'court' in title_metadata:
    judgment.court = title_metadata['court']
    judgment.save()
    print(f"\nUpdated court to: {judgment.court}")
else:
    print("\nNo court found in title metadata!") 