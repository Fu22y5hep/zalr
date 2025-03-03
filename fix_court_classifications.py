import os
import django
import sys
import time
from django.db import transaction

# Set up Django environment
sys.path.append('.')  # Add the current directory to path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalr_backend.settings')
django.setup()

# Import required models after Django setup
from semantis_app.models import Judgment
from semantis_app.utils.metadata import MetadataParser

def fix_court_classifications(batch_size=50):
    """
    Fix court classifications for all judgments based on their titles.
    This strictly uses the title for court extraction and doesn't fall back to text.
    """
    # Get all judgments with titles
    judgments = Judgment.objects.exclude(title='').all()
    total_judgments = judgments.count()
    
    print(f"Found {total_judgments} judgments with titles to process")
    
    # Start processing
    start_time = time.time()
    total_processed = 0
    total_updated = 0
    batch_number = 1
    
    # Process in batches
    while True:
        batch_start = (batch_number - 1) * batch_size
        batch_end = batch_start + batch_size
        batch_judgments = judgments[batch_start:batch_end]
        
        if not batch_judgments:
            break

        print(f"\nProcessing batch {batch_number}...")
        
        with transaction.atomic():
            batch_updated = 0
            for judgment in batch_judgments:
                # Extract metadata from title
                parser = MetadataParser(judgment.text_markdown, judgment.title)
                title_metadata = parser.parse_title()
                
                if 'court' in title_metadata:
                    # Check if court needs to be updated
                    if judgment.court != title_metadata['court']:
                        old_court = judgment.court or 'None'
                        judgment.court = title_metadata['court']
                        judgment.save()
                        batch_updated += 1
                        print(f"  Updated court: {old_court} → {judgment.court} for {judgment.title[:50]}...")
        
        total_processed += len(batch_judgments)
        total_updated += batch_updated
        
        # Update progress
        elapsed_time = time.time() - start_time
        avg_time = elapsed_time / total_processed if total_processed > 0 else 0
        progress = (total_processed / total_judgments) * 100
        
        print(
            f"Progress: {progress:.1f}% ({total_processed}/{total_judgments})\n"
            f"Updated in this batch: {batch_updated}\n"
            f"Total updated: {total_updated}\n"
            f"Average time per judgment: {avg_time:.2f} seconds\n"
            f"Elapsed time: {elapsed_time:.2f} seconds"
        )
        
        batch_number += 1
    
    # Final summary
    print(
        f"\nCompleted processing {total_processed} judgments\n"
        f"Total courts updated: {total_updated}\n"
        f"Total time: {time.time() - start_time:.2f} seconds"
    )

if __name__ == "__main__":
    # Run the function with default batch size
    fix_court_classifications() 