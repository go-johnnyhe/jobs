"""Configuration for job tracker."""

import os

# Discord webhook URL from environment variable
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Target companies with their career page URLs and ATS type
COMPANIES = {
    "Google": {
        "url": "https://careers.google.com/jobs/results/?employment_type=FULL_TIME&q=software%20engineer%20new%20grad",
        "ats": "internal",
    },
    "Meta": {
        "url": "https://www.metacareers.com/jobs?roles[0]=full-time&teams[0]=Software%20Engineering",
        "ats": "internal",
    },
    "Amazon": {
        "url": "https://www.amazon.jobs/en/search?base_query=software+engineer+new+grad",
        "ats": "internal",
    },
    "Apple": {
        "url": "https://jobs.apple.com/en-us/search?sort=newest&search=software%20engineer%20new%20grad",
        "ats": "internal",
    },
    "Netflix": {
        "url": "https://jobs.netflix.com/search?q=software%20engineer",
        "ats": "lever",
    },
    "Airbnb": {
        "url": "https://careers.airbnb.com/positions/?department=engineering",
        "ats": "greenhouse",
    },
    "Rubrik": {
        "url": "https://www.rubrik.com/company/careers/departments/job-openings",
        "ats": "greenhouse",
    },
}

# GitHub repositories to monitor
GITHUB_REPOS = [
    {
        "owner": "SimplifyJobs",
        "repo": "New-Grad-Positions",
        "file": "README.md",
    },
]

# Keywords to match in job titles (case-insensitive)
TITLE_KEYWORDS = [
    "new grad",
    "new graduate",
    "entry level",
    "entry-level",
    "junior",
    "university",
    "2024",
    "2025",
    "2026",
    "early career",
    "associate",
]

# Keywords that must be present (at least one)
ROLE_KEYWORDS = [
    "software",
    "engineer",
    "developer",
    "swe",
    "backend",
    "frontend",
    "full stack",
    "fullstack",
]

# Location preferences (empty list = all locations)
PREFERRED_LOCATIONS = [
    "seattle",
    "remote",
    "united states",
    "usa",
    "us",
    "san francisco",
    "new york",
    "mountain view",
    "palo alto",
    "sunnyvale",
    "menlo park",
]

# Companies to specifically track (for filtering GitHub repo results)
TARGET_COMPANIES = [
    "google",
    "meta",
    "facebook",
    "amazon",
    "apple",
    "netflix",
    "airbnb",
    "rubrik",
    "microsoft",
    "stripe",
    "coinbase",
    "databricks",
    "figma",
    "notion",
    "discord",
    "snap",
    "uber",
    "lyft",
    "doordash",
    "instacart",
    "robinhood",
    "plaid",
]

# SQLite database path
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")
