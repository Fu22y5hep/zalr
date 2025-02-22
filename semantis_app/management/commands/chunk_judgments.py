from django.core.management.base import BaseCommand, CommandError
from semantis_app.utils.chunking import process_pending_judgments
from django.db import transaction

class Command(BaseCommand):
    help = 'Create chunks for judgments that have not been chunked yet'

    def add_arguments(self, parser):
        parser.add_argument(
            '--judgment-id',
            type=str,
            help='Process only this specific judgment ID (optional)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of judgments to process in one batch (default: 10)',
        )

    def handle(self, *args, **options):
        try:
            self.stdout.write(self.style.SUCCESS('Starting chunking process...'))
            
            judgment_id = options.get('judgment_id')
            if judgment_id:
                from semantis_app.utils.chunking import chunk_judgment
                try:
                    chunks = chunk_judgment(judgment_id)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Successfully created {len(chunks)} chunks for judgment {judgment_id}'
                        )
                    )
                except ValueError as e:
                    raise CommandError(str(e))
            else:
                processed = process_pending_judgments()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully processed {processed} judgments'
                    )
                )
            
        except Exception as e:
            raise CommandError(f'Error during chunking process: {str(e)}') 