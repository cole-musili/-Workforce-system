
from django.core.management.base import BaseCommand, CommandError

from apps.duplicates.services.detector import scan_duplicates


class Command(BaseCommand):
    help = "Scan employee records and identify possible duplicates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-archived",
            action="store_true",
            help="Include archived employees in the duplicate scan.",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.NOTICE("Starting employee duplicate scan...")
        )

        try:
            results = scan_duplicates(
                include_archived=options["include_archived"]
            )
        except Exception as exc:
            raise CommandError(
                f"Duplicate scan failed: {exc}"
            ) from exc

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("Duplicate scan completed.")
        )

        self.stdout.write(f"Employees scanned: {results['employees_scanned']}")
        self.stdout.write(f"Matches detected: {results['matches_detected']}")
        self.stdout.write(f"Groups created: {results['groups_created']}")
        self.stdout.write(f"Groups updated: {results['groups_updated']}")
        self.stdout.write(f"Candidates created: {results['candidates_created']}")

        self.stdout.write("")
        self.stdout.write(
            "No employee records have been deleted or archived."
        )
