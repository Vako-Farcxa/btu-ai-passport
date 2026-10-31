"""Report students and versions left half-written by the old non-atomic sync (read only).

Usage (run in backend/, which reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from .env):
    uv run python scripts/check_consistency.py

Prints one line per problem and exits 1 if there are any. It never changes data.
"""

import sys

from passport_api.consistency import find_inconsistencies, load_students


def main() -> int:
    students = load_students()
    problems = find_inconsistencies(students)
    print(f"Checked {len(students)} students.")
    for problem in problems:
        version = "-" if problem.version_number is None else f"v{problem.version_number}"
        print(f"{problem.kind}\t{problem.passport_id}\t{version}\t{problem.detail}")
    print(f"{len(problems)} problem(s) found.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
