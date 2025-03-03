import os
import django
import sys

# Set up Django environment
sys.path.append('.')  # Add the current directory to path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalr_backend.settings')
django.setup()

# Import required models after Django setup
from semantis_app.models import Judgment
from collections import Counter

# Count court occurrences
court_counts = Counter([j.court for j in Judgment.objects.all() if j.court])

# Print results
print('Court distribution:')
for court, count in court_counts.most_common():
    print(f'{court}: {count}') 