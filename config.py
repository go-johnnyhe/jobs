"""Configuration for job tracker."""

import os

# Discord webhook URL from environment variable
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Target companies with their career page URLs and ATS type
COMPANIES = {
    # Big Tech
    "Google": {
        "url": "https://www.google.com/about/careers/applications/jobs/results/?employment_type=FULL_TIME&q=software%20engineer&target_level=EARLY",
        "ats": "google",
    },
    "Meta": {
        "url": "https://www.metacareers.com/jobsearch/?teams[0]=University%20Grad%20-%20Engineering%2C%20Tech%20%26%20Design&roles[0]=full-time",
        "ats": "meta",
    },
    "Amazon": {
        "url": "https://www.amazon.jobs/en/search?base_query=software+engineer+new+grad",
        "ats": "amazon",
        "search_queries": [
            "Software Development Engineer 2026",
            "Software Development Engineer 2027",
            "Software Development Engineer I",
            "Software Engineer 1",
        ],
    },
    "Apple": {
        "url": "https://jobs.apple.com/en-us/search",
        "ats": "apple",
        "search_queries": [
            "new grad software engineer",
            "entry level software engineer",
            "early career software engineer",
            "university graduate software engineer",
            "associate software engineer",
            "junior software engineer",
            "software engineer i",
            "software engineer 1",
            "2026 software engineer",
            "2027 software engineer",
        ],
    },
    "Netflix": {
        "url": "https://explore.jobs.netflix.net",
        "ats": "eightfold_apply",
        "ats_id": "netflix.com",
        "search_queries": ["software engineer"],
    },
    "Microsoft": {
        "url": "https://apply.careers.microsoft.com",
        "ats": "eightfold",
        "ats_id": "microsoft.com",
        "search_queries": ["software engineer"],
        "search_location": "United States",
    },
    "Stripe": {
        "url": "https://stripe.com/jobs/search?teams=Engineering",
        "ats": "structured_html",
        "site_parser": "stripe",
    },
    "Block": {
        "url": "https://block.xyz/careers?teams=Engineering",
        "ats": "greenhouse",
        "ats_id": "block",
    },
    # Cloud & Infrastructure
    "Cloudflare": {
        "url": "https://www.cloudflare.com/careers/jobs/?department=Engineering",
        "ats": "greenhouse",
        "ats_id": "cloudflare",
    },
    "HashiCorp": {
        "url": "https://www.ibm.com/careers/search?department=Engineering&q=hashicorp",
        "ats": "ibm_search",
        "search_query": "hashicorp",
        "required_posting_term": "hashicorp",
    },
    "Datadog": {
        "url": "https://careers.datadoghq.com/all-jobs/?team=Engineering",
        "ats": "greenhouse",
        "ats_id": "datadog",
    },
    "Confluent": {
        "url": "https://careers.confluent.io/jobs/engineering?engineering=engineering",
        "ats": "structured_html",
        "site_parser": "confluent",
    },
    "CockroachLabs": {
        "url": "https://boards.greenhouse.io/cockroachlabs",
        "ats": "greenhouse",
        "ats_id": "cockroachlabs",
    },
    "PlanetScale": {
        "url": "https://planetscale.com/careers#positions",
        "ats": "greenhouse",
        "ats_id": "planetscale",
    },
    "Temporal": {
        "url": "https://temporal.io/careers#open-positions",
        "ats": "greenhouse",
        "ats_id": "temporaltechnologies",
    },
    "Snowflake": {
        "url": "https://careers.snowflake.com/us/en/search-results?keywords=software%20engineer",
        "ats": "ashby",
        "ats_id": "snowflake",
    },
    # Developer Tools
    "GitHub": {
        "url": "https://www.github.careers/careers-home/jobs?categories=Engineering",
        "ats": "internal",
    },
    "GitLab": {
        "url": "https://about.gitlab.com/jobs/all-jobs/?department=Engineering",
        "ats": "greenhouse",
        "ats_id": "gitlab",
    },
    "Vercel": {
        "url": "https://vercel.com/careers#open-positions",
        "ats": "greenhouse",
        "ats_id": "vercel",
    },
    "Netlify": {
        "url": "https://www.netlify.com/careers/#perfect-job",
        "ats": "greenhouse",
        "ats_id": "netlify",
    },
    "Supabase": {
        "url": "https://supabase.com/careers#positions",
        "ats": "ashby",
        "ats_id": "supabase",
    },
    "Linear": {
        "url": "https://linear.app/careers#open-roles",
        "ats": "ashby",
        "ats_id": "Linear",
    },
    "Replit": {
        "url": "https://replit.com/site/careers",
        "ats": "ashby",
        "ats_id": "replit",
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
        "url": "https://ffive.wd5.myworkdayjobs.com/f5jobs",
        "ats": "workday",
    },
    # High-Growth Startups
    "Flyio": {
        "url": "https://fly.io/jobs/",
        "ats": "atom",
        "feed_url": "https://fly.io/jobs/feed.xml",
    },
    "Railway": {
        "url": "https://railway.com/careers",
        "ats": "structured_html",
        "site_parser": "railway",
    },
    "Render": {
        "url": "https://render.com/careers#open-positions",
        "ats": "ashby",
        "ats_id": "render",
    },
    # Existing
    "Airbnb": {
        "url": "https://careers.airbnb.com/positions/?department=engineering",
        "ats": "greenhouse",
        "ats_id": "airbnb",
    },
    "Rubrik": {
        "url": "https://www.rubrik.com/company/careers/departments/job-openings",
        "ats": "greenhouse",
        "ats_id": "rubrik",
    },
    # Fintech
    "Plaid": {
        "url": "https://plaid.com/careers/",
        "ats": "structured_html",
        "site_parser": "plaid",
    },
    "Robinhood": {
        "url": "https://boards.greenhouse.io/robinhood",
        "ats": "greenhouse",
        "ats_id": "robinhood",
    },
    "Coinbase": {
        "url": "https://www.coinbase.com/careers/positions",
        "ats": "greenhouse",
        "ats_id": "coinbase",
    },
    "Affirm": {
        "url": "https://boards.greenhouse.io/affirm",
        "ats": "greenhouse",
        "ats_id": "affirm",
    },
    "Brex": {
        "url": "https://www.brex.com/careers#joblist",
        "ats": "greenhouse",
        "ats_id": "brex",
    },
    "Ramp": {
        "url": "https://ramp.com/careers#openings",
        "ats": "ashby",
        "ats_id": "ramp",
    },
    "Chime": {
        "url": "https://boards.greenhouse.io/chime",
        "ats": "greenhouse",
        "ats_id": "chime",
    },
    "SoFi": {
        "url": "https://boards.greenhouse.io/sofi",
        "ats": "greenhouse",
        "ats_id": "sofi",
    },
    # Cloud/Data Infrastructure
    "Databricks": {
        "url": "https://www.databricks.com/company/careers/open-positions",
        "ats": "greenhouse",
        "ats_id": "databricks",
    },
    "MongoDB": {
        "url": "https://www.mongodb.com/careers/jobs",
        "ats": "greenhouse",
        "ats_id": "mongodb",
    },
    "Elastic": {
        "url": "https://jobs.elastic.co/jobs/department/engineering",
        "ats": "greenhouse",
        "ats_id": "elastic",
    },
    "DigitalOcean": {
        "url": "https://boards.greenhouse.io/digitalocean98",
        "ats": "greenhouse",
        "ats_id": "digitalocean98",
    },
    "Grafana": {
        "url": "https://grafana.com/about/careers/open-positions/",
        "ats": "greenhouse",
        "ats_id": "grafanalabs",
    },
    # Dev Tools & Productivity
    "Figma": {
        "url": "https://www.figma.com/careers/#job-openings",
        "ats": "greenhouse",
        "ats_id": "figma",
    },
    "Notion": {
        "url": "https://www.notion.so/careers#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "ashby",
        "ats_id": "notion",
    },
    "Postman": {
        "url": "https://www.postman.com/company/careers/open-positions/",
        "ats": "greenhouse",
        "ats_id": "postman",
    },
    "Atlassian": {
        "url": "https://www.atlassian.com/company/careers/all-jobs",
        "ats": "internal",
    },
    "Twilio": {
        "url": "https://www.twilio.com/en-us/company/jobs",
        "ats": "greenhouse",
        "ats_id": "twilio",
    },
    "Miro": {
        "url": "https://miro.com/careers/open-positions/",
        "ats": "miro",
    },
    "Retool": {
        "url": "https://retool.com/careers",
        "ats": "structured_html",
        "site_parser": "retool",
    },
    "Airtable": {
        "url": "https://airtable.com/careers#openings",
        "ats": "greenhouse",
        "ats_id": "airtable",
    },
    # Consumer Tech
    "Uber": {
        "url": "https://iaziqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/UberCareers",
        "ats": "oracle_ce",
        "api_url": "https://iaziqy.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "site_number": "CX_1",
    },
    "Lyft": {
        "url": "https://www.lyft.com/careers#openings",
        "ats": "greenhouse",
        "ats_id": "lyft",
    },
    "DoorDash": {
        "url": "https://boards.greenhouse.io/doordashusa",
        "ats": "greenhouse",
        "ats_id": "doordashusa",
    },
    "Instacart": {
        "url": "https://boards.greenhouse.io/instacart",
        "ats": "greenhouse",
        "ats_id": "instacart",
    },
    "Discord": {
        "url": "https://discord.com/jobs?team=engineering",
        "ats": "greenhouse",
        "ats_id": "discord",
    },
    "Spotify": {
        "url": "https://www.lifeatspotify.com/jobs?c=engineering",
        "ats": "spotify",
    },
    "Reddit": {
        "url": "https://www.redditinc.com/careers?team=engineering",
        "ats": "greenhouse",
        "ats_id": "reddit",
    },
    "Pinterest": {
        "url": "https://www.pinterestcareers.com/en/jobs/?team=Engineering",
        "ats": "greenhouse",
        "ats_id": "pinterest",
    },
    "Snap": {
        "url": "https://wd1.myworkdaysite.com/recruiting/snapchat/snap",
        "ats": "workday",
    },
    "Twitter": {
        "url": "https://x.com/careers",
        "ats": "internal",
    },
    # Seattle Tech
    "Redfin": {
        "url": "https://careers.rocket.com/us/en",
        "ats": "phenom",
        # Searching the brand returns the complete Redfin subset of Rocket jobs.
        "search_queries": ["Redfin"],
        "posting_company_names": ["Redfin Corporation"],
    },
    "Qualtrics": {
        "url": "https://www.qualtrics.com/careers/us/en",
        "ats": "phenom",
        "search_queries": ["software"],
    },
    # AI/ML Companies
    "Anthropic": {
        "url": "https://www.anthropic.com/careers#open-roles",
        "ats": "greenhouse",
        "ats_id": "anthropic",
    },
    "OpenAI": {
        "url": "https://openai.com/careers/search",
        "ats": "ashby",
        "ats_id": "openai",
    },
    "ScaleAI": {
        "url": "https://scale.com/careers",
        "ats": "greenhouse",
        "ats_id": "scaleai",
    },
    "Cohere": {
        "url": "https://cohere.com/careers#open-roles",
        "ats": "ashby",
        "ats_id": "cohere",
    },
    "Hugging Face": {
        "url": "https://apply.workable.com/huggingface",
        "ats": "workable",
        "ats_id": "huggingface",
    },
    # Enterprise Software
    "Salesforce": {
        "url": "https://www.salesforce.com/company/careers/jobs/",
        "ats": "salesforce",
    },
    "Adobe": {
        "url": "https://adobe.wd5.myworkdayjobs.com/external_experienced",
        "ats": "workday",
    },
    "Okta": {
        "url": "https://www.okta.com/company/careers/#job-openings",
        "ats": "greenhouse",
        "ats_id": "okta",
    },
    "CrowdStrike": {
        "url": "https://crowdstrike.wd5.myworkdayjobs.com/CrowdStrikeCareers",
        "ats": "workday",
    },
    "ServiceNow": {
        "url": "https://careers.servicenow.com/en/jobs/",
        "ats": "smartrecruiters",
        "ats_id": "ServiceNow",
    },
    "Palantir": {
        "url": "https://www.palantir.com/careers/",
        "ats": "lever",
        "ats_id": "palantir",
    },
    "Splunk": {
        "url": "https://careers.cisco.com/global/en",
        "ats": "phenom",
        "search_queries": ["Splunk"],
        "required_posting_terms": ["splunk"],
    },
    "Palo Alto Networks": {
        "url": "https://paloaltonetworks.wd5.myworkdayjobs.com/panwexternalcareers",
        "ats": "workday",
    },
    # Quant/Trading
    "Jane Street": {
        "url": "https://www.janestreet.com/join-jane-street/open-roles/",
        "ats": "jane_street",
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
        "ats": "internal",
    },
    "DE Shaw": {
        "url": "https://www.deshaw.com/careers",
        "ats": "internal",
    },
    "Optiver": {
        "url": "https://www.optiver.com/join-us/jobs/",
        "ats": "optiver",
    },
    # E-commerce/Retail Tech
    "Shopify": {
        "url": "https://www.shopify.com/careers?teams%5B%5D=engineering",
        "ats": "structured_html",
        "site_parser": "shopify",
    },
    "Etsy": {
        "url": "https://careers.etsy.com/en",
        "ats": "internal",
    },
    "Wayfair": {
        "url": "https://www.wayfair.com/careers/jobs?teamIds=6&gh_jid=",
        "ats": "internal",
    },
    "Chewy": {
        "url": "https://careers.chewy.com",
        "ats": "phenom",
        "search_queries": ["software", "engineer"],
        "search_country": "us",
        "search_locale": "en_us",
    },
    # Gaming
    "Roblox": {
        "url": "https://careers.roblox.com/jobs?teams=Engineering",
        "ats": "greenhouse",
        "ats_id": "roblox",
    },
    "Epic Games": {
        "url": "https://boards.greenhouse.io/epicgames",
        "ats": "greenhouse",
        "ats_id": "epicgames",
    },
    "Riot Games": {
        "url": "https://www.riotgames.com/en/work-with-us/jobs#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "greenhouse",
        "ats_id": "riotgames",
    },
    # Misc High-Growth
    "Gusto": {
        "url": "https://gusto.com/about/careers#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "greenhouse",
        "ats_id": "gusto",
    },
    "Rippling": {
        "url": "https://www.rippling.com/careers/open-roles",
        "ats": "rippling",
        "ats_id": "careers_en-US_production",
        "algolia_app_id": "6FNAX3TBEF",
        # Public, search-only browser key embedded in Rippling's careers app.
        "algolia_public_search_key": "416caa4690f002ff6fe4a2097623640b",
    },
    "Navan": {
        "url": "https://navan.com/careers#702a6c37c14845ae9b51a5e4f5ea4d18",
        "ats": "greenhouse",
        "ats_id": "tripactions",
    },
    "Zapier": {
        "url": "https://zapier.com/jobs",
        "ats": "ashby",
        "ats_id": "Zapier",
    },
    "Asana": {
        "url": "https://asana.com/jobs/all",
        "ats": "greenhouse",
        "ats_id": "asana",
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

# Career-page results are noisy; require an explicit early-career signal there.
CAREER_ENTRY_LEVEL_KEYWORDS = [
    "new grad",
    "new graduate",
    "university grad",
    "university graduate",
    "graduate software",
    "software engineer i",
    "software engineer 1",
    "sde i",
    "sde 1",
    "swe i",
    "swe 1",
    "entry level",
    "entry-level",
    "early career",
    "early-career",
    "junior",
    "associate software engineer",
    "2026",
    "2027",
]

# Generic career pages often mix real openings with articles and employee stories.
CAREER_CONTENT_EXCLUSIONS = [
    "blog",
    "culture",
    "life at",
    "meet ",
    "shares ",
    "why ",
    "welcome",
    "hackathon",
    "intern to full-time",
    "my first year",
    "working at",
    "what it's like",
    "career journey",
    "sales onboarding",
    "systems engineering at",
    "systems engineer experience",
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

# Critical companies to surface with company-level health alerts/stats.
PRIORITY_COMPANIES = [
    "Google",
    "Meta",
    "Microsoft",
    "Apple",
    "Amazon",
]

# Consecutive-failure counts that trigger source health alerts.
SOURCE_FAILURE_ALERT_THRESHOLDS = [3, 6, 12]

# Company-level alerts should fire once per failure streak, then recover.
COMPANY_FAILURE_ALERT_THRESHOLDS = [3]

# Company scrape failures are noisy and often mean a career page changed, not
# that the job tracker itself is broken. Keep these in stats/logs by default.
ENABLE_COMPANY_HEALTH_ALERTS = False

# Career source is considered healthy only if enough company scrapes succeed.
CAREERS_MIN_HEALTHY_SUCCESS_RATE = 0.25
CAREERS_MIN_HEALTHY_SUCCESSES = 5

# Career pages are independent; bounded concurrency keeps one slow or blocked
# company from delaying the entire hourly run.
CAREERS_MAX_WORKERS = 8

# Seniority exclusions - keywords that indicate non-entry-level positions
SENIORITY_EXCLUSIONS = [
    "senior", "staff", "principal", "principle", "lead", "manager", "director", "sr.", "sr ",
]

# Title exclusions - keywords that indicate non-software engineering roles
# Note: Data/ML/AI Engineer and DevOps/SRE/Platform Engineer are intentionally allowed
TITLE_EXCLUSIONS = [
    # Internships are tracked separately from full-time new-grad roles.
    "intern",
    # Sales-adjacent roles
    "sales engineer",
    "systems engineer",
    "system engineer",
    "sales team",
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
    "network operations",
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
