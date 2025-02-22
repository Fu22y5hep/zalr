from django.core.management.base import BaseCommand
from semantis_app.tests.test_embedding import test_embedding_generation

class Command(BaseCommand):
    help = 'Test the embedding generator with a sample text'

    def handle(self, *args, **options):
        self.stdout.write('Starting embedding test...')
        test_embedding_generation()
        self.stdout.write(self.style.SUCCESS('Embedding test completed')) 