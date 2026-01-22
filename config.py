"""Configuration for job tracker."""

import os

# Discord webhook URL from environment variable
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Target companies with their career page URLs and ATS type
COMPANIES = {
    # Big Tech
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
    "Microsoft": {
        "url": "https://careers.microsoft.com/us/en/search-results?keywords=software%20engineer%20new%20grad",
        "ats": "internal",
    },
    "Stripe": {
        "url": "https://stripe.com/jobs/search?teams=Engineering",
        "ats": "internal",
    },
    "Block": {
        "url": "https://block.xyz/careers?teams=Engineering",
        "ats": "greenhouse",
    },
    # Cloud & Infrastructure
    "Cloudflare": {
        "url": "https://www.cloudflare.com/careers/jobs/?department=Engineering",
        "ats": "greenhouse",
    },
    "HashiCorp": {
        "url": "https://www.hashicorp.com/careers/open-positions?department=Engineering",
        "ats": "greenhouse",
    },
    "Datadog": {
        "url": "https://careers.datadoghq.com/all-jobs/?team=Engineering",
        "ats": "greenhouse",
    },
    "Confluent": {
        "url": "https://careers.confluent.io/search/engineering/jobs",
        "ats": "greenhouse",
    },
    "CockroachLabs": {
        "url": "https://www.cockroachlabs.com/careers/jobs/",
        "ats": "greenhouse",
    },
    "PlanetScale": {
        "url": "https://planetscale.com/careers#positions",
        "ats": "lever",
    },
    "Temporal": {
        "url": "https://temporal.io/careers#open-positions",
        "ats": "greenhouse",
    },
    "Snowflake": {
        "url": "https://careers.snowflake.com/us/en/search-results?keywords=software%20engineer",
        "ats": "internal",
    },
    # Developer Tools
    "GitHub": {
        "url": "https://www.github.careers/careers-home/jobs?categories=Engineering",
        "ats": "internal",
    },
    "GitLab": {
        "url": "https://about.gitlab.com/jobs/all-jobs/?department=Engineering",
        "ats": "greenhouse",
    },
    "Vercel": {
        "url": "https://vercel.com/careers#open-positions",
        "ats": "greenhouse",
    },
    "Netlify": {
        "url": "https://www.netlify.com/careers/#perfect-job",
        "ats": "greenhouse",
    },
    "Supabase": {
        "url": "https://supabase.com/careers#positions",
        "ats": "lever",
    },
    "Linear": {
        "url": "https://linear.app/careers#open-roles",
        "ats": "lever",
    },
    "Replit": {
        "url": "https://replit.com/site/careers",
        "ats": "greenhouse",
    },
    # Seattle Companies
    "Expedia": {
        "url": "https://careers.expediagroup.com/jobs/?filter[category]=Technology",
        "ats": "internal",
    },
    "Zillow": {
        "url": "https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External?q=software%20engineer",
        "ats": "workday",
    },
    "F5": {
        "url": "https://f5.recsolu.com/jobs?per_page=20",
        "ats": "internal",
    },
    # High-Growth Startups
    "Flyio": {
        "url": "https://fly.io/jobs/",
        "ats": "internal",
    },
    "Railway": {
        "url": "https://railway.app/careers",
        "ats": "lever",
    },
    "Render": {
        "url": "https://render.com/careers#open-positions",
        "ats": "greenhouse",
    },
    # Existing
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
    # Big Tech
    "google",
    "meta",
    "facebook",
    "amazon",
    "apple",
    "netflix",
    "microsoft",
    "stripe",
    "block",
    "square",
    # Cloud & Infrastructure
    "cloudflare",
    "hashicorp",
    "datadog",
    "confluent",
    "cockroach",
    "cockroachlabs",
    "planetscale",
    "temporal",
    "snowflake",
    # Developer Tools
    "github",
    "gitlab",
    "vercel",
    "netlify",
    "supabase",
    "linear",
    "replit",
    # Seattle Companies
    "expedia",
    "zillow",
    "f5",
    # High-Growth Startups
    "fly.io",
    "flyio",
    "railway",
    "render",
    # Existing from before
    "airbnb",
    "rubrik",
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
