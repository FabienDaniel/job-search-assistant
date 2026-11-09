"""`python -m backend.refresh_linkedin_session`: the sign-in command error messages and the
changelog give users. The code lives in backend/scraper/_shared/linkedin_session.py."""

import sys

from backend.scraper._shared.linkedin_session import main

if __name__ == "__main__":
    sys.exit(main())
