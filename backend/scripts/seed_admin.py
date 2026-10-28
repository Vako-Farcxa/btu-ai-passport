"""Seed the first admin user (idempotent).

Usage:
    uv run python scripts/seed_admin.py admin@btu.edu.ge

The script inserts the given email into admin_users.  Running it again for
the same email is a no-op (upsert on conflict ignore).
"""

import os
import sys

from supabase import create_client


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: seed_admin.py <admin@btu.edu.ge>", file=sys.stderr)
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    if not email.endswith("@btu.edu.ge"):
        print(f"Error: email must end with @btu.edu.ge, got {email!r}", file=sys.stderr)
        sys.exit(1)

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)

    client.table("admin_users").upsert(
        {"email": email},
        on_conflict="email",
        ignore_duplicates=True,
    ).execute()

    print(f"Admin user ensured: {email}")


if __name__ == "__main__":
    main()
