from django.core.management.base import BaseCommand
from semantis_app.utils.scraping import scrape_court_year, ScrapingError

class Command(BaseCommand):
    help = 'Test the scraping functionality by scraping judgments from a specific court and year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--court',
            type=str,
            help='Court code (e.g., ZACC for Constitutional Court)',
            required=True
        )
        parser.add_argument(
            '--year',
            type=int,
            help='Year to scrape (e.g., 2024)',
            required=True
        )

    def handle(self, *args, **options):
        try:
            court = options['court']
            year = options['year']
            
            self.stdout.write(self.style.SUCCESS(
                f"Attempting to scrape judgments from {court} for year {year}"
            ))
            
            judgments = scrape_court_year(court, year)
            
            if judgments:
                self.stdout.write(self.style.SUCCESS(
                    f"\nSuccessfully scraped {len(judgments)} judgments:"
                ))
                for judgment in judgments:
                    self.stdout.write(self.style.SUCCESS(
                        f"\nTitle: {judgment.title}"
                        f"\nURL: {judgment.saflii_url}"
                        f"\nText length: {len(judgment.text_markdown)} characters"
                        f"\n---"
                    ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"No new judgments found for {court} in {year}"
                ))

        except ScrapingError as e:
            self.stdout.write(self.style.ERROR(f"Scraping error: {str(e)}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Unexpected error: {str(e)}")) 