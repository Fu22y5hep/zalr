from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from semantis_app.models import Judgment
from django.db import transaction

class Command(BaseCommand):
    help = 'Updates the featured judgment to the highest scoring judgment from the current week'

    def handle(self, *args, **options):
        with transaction.atomic():
            # First, unset all featured judgments
            Judgment.objects.filter(featured=True).update(featured=False)

            # Get the date range for the current week
            today = timezone.now().date()
            start_of_week = today - timedelta(days=today.weekday())  # Monday
            end_of_week = start_of_week + timedelta(days=6)  # Sunday

            # Find the highest scoring judgment from this week
            highest_scoring = Judgment.objects.filter(
                judgment_date__range=(start_of_week, end_of_week),
                reportability_score__gt=0  # Only consider scored judgments
            ).order_by('-reportability_score').first()

            if highest_scoring:
                highest_scoring.featured = True
                highest_scoring.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully set featured judgment to: {highest_scoring.title} '
                        f'(Score: {highest_scoring.reportability_score})'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'No judgments found for the current week with reportability scores'
                    )
                ) 