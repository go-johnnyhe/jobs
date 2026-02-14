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
        "url": "https://www.netflix.com/jobs",
        "ats": "internal",
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
        "url": "https://boards.greenhouse.io/cockroachlabs",
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
        "url": "https://www.f5.com/company/careers",
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
    # Fintech
    "Plaid": {
        "url": "https://plaid.com/careers/openings/",
        "ats": "lever",
    },
    "Robinhood": {
        "url": "https://boards.greenhouse.io/robinhood",
        "ats": "greenhouse",
    },
    "Coinbase": {
        "url": "https://www.coinbase.com/careers/positions",
        "ats": "greenhouse",
    },
    "Affirm": {
        "url": "https://boards.greenhouse.io/affirm",
        "ats": "greenhouse",
    },
    "Brex": {
        "url": "https://www.brex.com/careers#joblist",
        "ats": "greenhouse",
    },
    "Ramp": {
        "url": "https://ramp.com/careers#openings",
        "ats": "greenhouse",
    },
    "Chime": {
        "url": "https://boards.greenhouse.io/chime",
        "ats": "greenhouse",
    },
    "SoFi": {
        "url": "https://boards.greenhouse.io/sofi",
        "ats": "greenhouse",
    },
    # Cloud/Data Infrastructure
    "Databricks": {
        "url": "https://www.databricks.com/company/careers/open-positions",
        "ats": "greenhouse",
    },
    "MongoDB": {
        "url": "https://www.mongodb.com/careers/jobs",
        "ats": "greenhouse",
    },
    "Elastic": {
        "url": "https://jobs.elastic.co/jobs/department/engineering",
        "ats": "greenhouse",
    },
    "DigitalOcean": {
        "url": "https://boards.greenhouse.io/digitalocean98",
        "ats": "greenhouse",
    },
    "Grafana": {
        "url": "https://grafana.com/about/careers/open-positions/",
        "ats": "lever",
    },
    # Dev Tools & Productivity
    "Figma": {
        "url": "https://www.figma.com/careers/#job-openings",
        "ats": "greenhouse",
    },
    "Notion": {
        "url": "https://www.notion.so/careers#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "lever",
    },
    "Postman": {
        "url": "https://www.postman.com/company/careers/open-positions/",
        "ats": "greenhouse",
    },
    "Atlassian": {
        "url": "https://www.atlassian.com/company/careers/all-jobs",
        "ats": "internal",
    },
    "Twilio": {
        "url": "https://www.twilio.com/en-us/company/jobs",
        "ats": "greenhouse",
    },
    "Miro": {
        "url": "https://miro.com/careers/open-positions/",
        "ats": "greenhouse",
    },
    "Retool": {
        "url": "https://retool.com/careers#jobs",
        "ats": "lever",
    },
    "Airtable": {
        "url": "https://airtable.com/careers#openings",
        "ats": "greenhouse",
    },
    # Consumer Tech
    "Uber": {
        "url": "https://www.uber.com/us/en/careers/list/?query=software%20engineer",
        "ats": "internal",
    },
    "Lyft": {
        "url": "https://www.lyft.com/careers#openings",
        "ats": "greenhouse",
    },
    "DoorDash": {
        "url": "https://boards.greenhouse.io/doordashusa",
        "ats": "greenhouse",
    },
    "Instacart": {
        "url": "https://boards.greenhouse.io/instacart",
        "ats": "greenhouse",
    },
    "Discord": {
        "url": "https://discord.com/jobs?team=engineering",
        "ats": "greenhouse",
    },
    "Spotify": {
        "url": "https://www.lifeatspotify.com/jobs?c=engineering",
        "ats": "internal",
    },
    "Reddit": {
        "url": "https://www.redditinc.com/careers?team=engineering",
        "ats": "greenhouse",
    },
    "Pinterest": {
        "url": "https://www.pinterestcareers.com/en/jobs/?team=Engineering",
        "ats": "greenhouse",
    },
    "Snap": {
        "url": "https://snap.com/en-US/jobs?teams=Engineering",
        "ats": "internal",
    },
    "Twitter": {
        "url": "https://x.com/careers",
        "ats": "internal",
    },
    # Seattle Tech
    "Redfin": {
        "url": "https://www.redfin.com/about/jobs",
        "ats": "greenhouse",
    },
    "Qualtrics": {
        "url": "https://www.qualtrics.com/careers/us/en/search-results",
        "ats": "internal",
    },
    # AI/ML Companies
    "Anthropic": {
        "url": "https://www.anthropic.com/careers#open-roles",
        "ats": "greenhouse",
    },
    "OpenAI": {
        "url": "https://openai.com/careers/search",
        "ats": "greenhouse",
    },
    "ScaleAI": {
        "url": "https://scale.com/careers",
        "ats": "lever",
    },
    "Cohere": {
        "url": "https://cohere.com/careers#open-roles",
        "ats": "greenhouse",
    },
    "Hugging Face": {
        "url": "https://huggingface.co/careers",
        "ats": "internal",
    },
    # Enterprise Software
    "Salesforce": {
        "url": "https://careers.salesforce.com/en/jobs/?search=software+engineer",
        "ats": "internal",
    },
    "Adobe": {
        "url": "https://careers.adobe.com/us/en/search-results?keywords=software%20engineer",
        "ats": "internal",
    },
    "Okta": {
        "url": "https://www.okta.com/company/careers/#job-openings",
        "ats": "greenhouse",
    },
    "CrowdStrike": {
        "url": "https://crowdstrike.wd5.myworkdayjobs.com/CrowdStrikeCareers",
        "ats": "workday",
    },
    "ServiceNow": {
        "url": "https://careers.servicenow.com/en/jobs/",
        "ats": "internal",
    },
    "Palantir": {
        "url": "https://www.palantir.com/careers/",
        "ats": "lever",
    },
    "Splunk": {
        "url": "https://www.splunk.com/en_us/careers.html",
        "ats": "internal",
    },
    "Palo Alto Networks": {
        "url": "https://jobs.paloaltonetworks.com/en",
        "ats": "internal",
    },
    # Quant/Trading
    "Jane Street": {
        "url": "https://www.janestreet.com/join-jane-street/open-roles/",
        "ats": "internal",
    },
    "Two Sigma": {
        "url": "https://www.twosigma.com/careers/",
        "ats": "internal",
    },
    "Citadel": {
        "url": "https://www.citadel.com/careers/open-opportunities/",
        "ats": "internal",
    },
    "HRT": {
        "url": "https://www.hudsonrivertrading.com/careers/",
        "ats": "greenhouse",
    },
    "DE Shaw": {
        "url": "https://www.deshaw.com/careers",
        "ats": "internal",
    },
    "Optiver": {
        "url": "https://optiver.com/working-at-optiver/career-opportunities/",
        "ats": "greenhouse",
    },
    # E-commerce/Retail Tech
    "Shopify": {
        "url": "https://www.shopify.com/careers/search?teams%5B%5D=engineering",
        "ats": "greenhouse",
    },
    "Etsy": {
        "url": "https://careers.etsy.com/en",
        "ats": "internal",
    },
    "Wayfair": {
        "url": "https://www.wayfair.com/careers/jobs?teamIds=6&gh_jid=",
        "ats": "greenhouse",
    },
    "Chewy": {
        "url": "https://careers.chewy.com/us/en/search-results?keywords=software",
        "ats": "internal",
    },
    # Gaming
    "Roblox": {
        "url": "https://careers.roblox.com/jobs?teams=Engineering",
        "ats": "greenhouse",
    },
    "Epic Games": {
        "url": "https://boards.greenhouse.io/epicgames",
        "ats": "greenhouse",
    },
    "Riot Games": {
        "url": "https://www.riotgames.com/en/work-with-us/jobs#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "greenhouse",
    },
    # Misc High-Growth
    "Gusto": {
        "url": "https://gusto.com/about/careers#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "greenhouse",
    },
    "Rippling": {
        "url": "https://www.rippling.com/careers/all-openings",
        "ats": "greenhouse",
    },
    "Navan": {
        "url": "https://navan.com/careers#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "greenhouse",
    },
    "Zapier": {
        "url": "https://zapier.com/jobs",
        "ats": "lever",
    },
    "Asana": {
        "url": "https://asana.com/jobs/all",
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

# Aliases for company matching on GitHub repo results.
# Keys must match COMPANIES keys. Values are extra lowercase match strings.
COMPANY_ALIASES = {
    "Meta": ["facebook"],
    "Block": ["square"],
    "CockroachLabs": ["cockroach"],
    "Flyio": ["fly.io"],
    "Snap": ["snapchat"],
    "Twitter": ["twitter"],
    "ScaleAI": ["scale"],
    "Hugging Face": ["huggingface"],
    "Palo Alto Networks": ["paloalto"],
    "Jane Street": ["janestreet"],
    "Two Sigma": ["twosigma"],
    "HRT": ["hudson river trading"],
    "DE Shaw": ["deshaw"],
    "Epic Games": ["epicgames"],
    "Riot Games": ["riot"],
    "Navan": ["tripactions"],
}

# Auto-derived from COMPANIES keys + COMPANY_ALIASES values
TARGET_COMPANIES = sorted(set(
    [name.lower() for name in COMPANIES]
    + [alias for aliases in COMPANY_ALIASES.values() for alias in aliases]
))

# Consecutive-failure counts that trigger source health alerts.
SOURCE_FAILURE_ALERT_THRESHOLDS = [3, 6, 12]

# Career source is considered healthy only if enough company scrapes succeed.
CAREERS_MIN_HEALTHY_SUCCESS_RATE = 0.25
CAREERS_MIN_HEALTHY_SUCCESSES = 5

# Seniority exclusions - keywords that indicate non-entry-level positions
SENIORITY_EXCLUSIONS = [
    "senior", "staff", "principal", "lead", "manager", "director", "sr.", "sr ",
]

# Title exclusions - keywords that indicate non-software engineering roles
# Note: Data/ML/AI Engineer and DevOps/SRE/Platform Engineer are intentionally allowed
TITLE_EXCLUSIONS = [
    # Sales-adjacent roles
    "sales engineer",
    "solutions engineer",
    "solutions architect",
    "customer engineer",
    "customer success",
    "field engineer",
    "pre-sales",
    "presales",
    # Mobile-specific (user wants web/backend focus)
    "android engineer",
    "android developer",
    "ios engineer",
    "ios developer",
    "mobile engineer",
    "mobile developer",
    # QA/Test roles
    "qa engineer",
    "quality assurance",
    "test engineer",
    "sdet",
    "automation engineer",
    "quality engineer",
    # Hardware/Embedded (not software)
    "hardware engineer",
    "embedded engineer",
    "firmware engineer",
    "electrical engineer",
    "mechanical engineer",
    "manufacturing engineer",
    # Support/Operations (not development)
    "support engineer",
    "it engineer",
    "network engineer",
    "systems administrator",
    "helpdesk",
    # Other non-SWE
    "security engineer",
    "application engineer",
    "implementation engineer",
    "integration engineer",
]

# Blocked locations - explicitly reject jobs in these locations
BLOCKED_LOCATIONS = [
    # UK
    "london",
    "cambridge",
    "manchester",
    "edinburgh",
    "bristol",
    "oxford",
    "united kingdom",
    "uk",
    "england",
    "scotland",
    # Europe
    "germany",
    "berlin",
    "munich",
    "frankfurt",
    "france",
    "paris",
    "ireland",
    "dublin",
    "netherlands",
    "amsterdam",
    "spain",
    "madrid",
    "barcelona",
    "italy",
    "switzerland",
    "zurich",
    "poland",
    "warsaw",
    "sweden",
    "stockholm",
    "denmark",
    "copenhagen",
    # India
    "india",
    "bangalore",
    "bengaluru",
    "hyderabad",
    "mumbai",
    "pune",
    "delhi",
    "gurgaon",
    "noida",
    "chennai",
    # APAC
    "singapore",
    "japan",
    "tokyo",
    "australia",
    "sydney",
    "melbourne",
    "china",
    "beijing",
    "shanghai",
    "hong kong",
    "taiwan",
    "korea",
    "seoul",
    # Canada
    "canada",
    "toronto",
    "vancouver",
    "montreal",
    "ottawa",
    "waterloo",
    # Latin America
    "brazil",
    "mexico",
    "argentina",
]

# Seniority exclusion patterns - regex patterns for detecting senior roles
SENIORITY_EXCLUSION_PATTERNS = [
    r'\b(?:sde|swe|engineer|developer)\s*[2-9]\b',       # SDE 2, Engineer 3
    r'\b(?:sde|swe|engineer|developer)\s*(?:ii|iii|iv|v)\b',  # SDE II, III
    r'\bl[4-9]\b',                                        # L4, L5, L6
    r'\blevel\s*[4-9]\b',                                # Level 4, Level 5
    r'\b[2-9]\+?\s*years?\b',                            # 2+ years experience
]

# SQLite database path
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")
