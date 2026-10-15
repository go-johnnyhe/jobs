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
        "ats": "greenhouse",
        "ats_id": "stripe",
    },
    "Block": {
        "url": "https://block.xyz/careers?teams=Engineering",
        "ats": "greenhouse",
        "ats_id": "block",
    },
    "NVIDIA": {
        "url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        "ats": "workday",
    },
    "LinkedIn": {
        "url": "https://job-boards.greenhouse.io/linkedin",
        "ats": "greenhouse",
        "ats_id": "linkedin",
    },
    "Oracle": {
        "url": "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/jobsearch/jobs",
        "ats": "oracle_ce",
        "api_url": "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "site_number": "CX_45001",
    },
    "Cisco": {
        "url": "https://careers.cisco.com/global/en",
        "ats": "phenom",
        "search_queries": [
            "software engineer",
            "software developer",
            "new grad software",
        ],
    },
    "Intel": {
        "url": "https://intel.wd1.myworkdayjobs.com/External",
        "ats": "workday",
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
        "ats": "ashby",
        "ats_id": "confluent",
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
        "ats": "ashby",
        "ats_id": "temporal",
    },
    "Snowflake": {
        "url": "https://careers.snowflake.com/us/en/search-results?keywords=software%20engineer",
        "ats": "ashby",
        "ats_id": "snowflake",
    },
    # Developer Tools
    "GitHub": {
        "url": "https://www.github.careers/careers-home/jobs?categories=Engineering",
        "ats": "jibe",
        "api_url": "https://www.github.careers/api/jobs",
        "search_category": "Engineering",
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
    "Dropbox": {
        "url": "https://job-boards.greenhouse.io/dropbox",
        "ats": "greenhouse",
        "ats_id": "dropbox",
    },
    # Seattle Companies
    "Expedia": {
        "url": "https://expedia.wd108.myworkdayjobs.com/search",
        "ats": "workday",
    },
    "Zillow": {
        "url": "https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External?q=software%20engineer",
        "ats": "workday",
    },
    "F5": {
        "url": "https://ffive.wd5.myworkdayjobs.com/f5jobs",
        "ats": "workday",
    },
    "Remitly": {
        "url": "https://remitly.wd5.myworkdayjobs.com/Remitly_Careers",
        "ats": "workday",
    },
    "T-Mobile": {
        # The unfiltered feed is mostly retail roles and Workday caps its
        # advertised total at 2000, so query the engineering subset instead.
        "url": "https://tmobile.wd1.myworkdayjobs.com/External",
        "ats": "workday",
        "search_queries": ["software", "developer", "engineer"],
    },
    "Smartsheet": {
        "url": "https://job-boards.greenhouse.io/smartsheet",
        "ats": "greenhouse",
        "ats_id": "smartsheet",
    },
    "Tanium": {
        "url": "https://job-boards.greenhouse.io/tanium",
        "ats": "greenhouse",
        "ats_id": "tanium",
    },
    "Nintendo": {
        "url": "https://job-boards.greenhouse.io/nintendo",
        "ats": "greenhouse",
        "ats_id": "nintendo",
    },
    "Outreach": {
        "url": "https://jobs.lever.co/outreach",
        "ats": "lever",
        "ats_id": "outreach",
    },
    "Qumulo": {
        "url": "https://jobs.ashbyhq.com/qumulo",
        "ats": "ashby",
        "ats_id": "qumulo",
    },
    "Truveta": {
        "url": "https://job-boards.greenhouse.io/truveta",
        "ats": "greenhouse",
        "ats_id": "truveta",
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
    "Capital One": {
        "url": "https://capitalone.wd12.myworkdayjobs.com/Capital_One",
        "ats": "workday",
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
        "ats": "jibe",
        "api_url": "https://join.atlassian.com/api/jobs",
        "search_category": "Engineering",
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
        # The old SmartRecruiters feed contains only 2024 postings. This
        # official page redirects to xAI, whose Greenhouse board is also
        # configured below. Keep blocked/incomplete coverage visible.
        "url": "https://careers.x.com",
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
    "xAI": {
        "url": "https://x.ai/careers",
        "ats": "greenhouse",
        "ats_id": "xai",
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
        "url": "https://careers.twosigma.com/careers/OpenRoles/",
        "ats": "two_sigma",
    },
    "Citadel": {
        "url": "https://www.citadel.com/careers/open-opportunities/",
        "ats": "internal",
    },
    "HRT": {
        "url": "https://www.hudsonrivertrading.com/careers/",
        "ats": "greenhouse",
        "ats_id": "wehrtyou",
    },
    "DE Shaw": {
        "url": "https://www.deshaw.com/careers",
        "ats": "de_shaw",
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
        "url": "https://careers.etsy.com/jobs/search",
        "ats": "etsy",
    },
    "Wayfair": {
        # SmartRecruiters only exposes a 2017 posting, not the current board.
        # Use the official source even when it reports a rate-limit failure.
        "url": "https://www.wayfair.com/careers/jobs",
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

# GitHub repositories to monitor. Both HTML-table and Markdown-table READMEs are
# parsed by header name, so column order changes do not break parsing.
GITHUB_REPOS = [
    {
        "owner": "SimplifyJobs",
        "repo": "New-Grad-Positions",
        "branch": "dev",
        "file": "README.md",
    },
    {
        # speedyapply renamed 2026-SWE-College-Jobs to this repository; the old
        # name redirects here. NEW_GRAD_USA.md holds the US new-grad tables.
        "owner": "speedyapply",
        "repo": "2027-SWE-College-Jobs",
        "branch": "main",
        "file": "NEW_GRAD_USA.md",
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
    "new college grad",
    "college grad",
    "college graduate",
    "recent grad",
    "recent graduate",
    "university grad",
    "university graduate",
    "graduate software",
    "graduate engineer",
    "software engineer i",
    "software engineer 1",
    "software developer i",
    "software developer 1",
    "sde i",
    "sde 1",
    "swe i",
    "swe 1",
    "engineer i",
    "engineer 1",
    "developer i",
    "developer 1",
    "entry level",
    "entry-level",
    "early career",
    "early-career",
    "junior",
    "associate software engineer",
    "associate software developer",
    "campus hire",
    "campus graduate",
    "2026",
    "2027",
    "2028",
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
    "bellevue",
    "redmond",
    "kirkland",
    "remote",
    "united states",
    "usa",
    "us",
    "san francisco",
    "sf",
    "new york",
    "nyc",
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
    "xAI": ["x.ai"],
    "T-Mobile": ["tmobile"],
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
    "NVIDIA",
    "LinkedIn",
    "Netflix",
    "GitHub",
    "Stripe",
    "OpenAI",
    "Anthropic",
    "xAI",
]

# Consecutive-failure counts that trigger source health alerts.
SOURCE_FAILURE_ALERT_THRESHOLDS = [3, 6, 12]

# Company-level alerts should fire once per failure streak, then recover.
COMPANY_FAILURE_ALERT_THRESHOLDS = [3]

# Keep company failures in logs and statistics. Do not send them to Discord;
# Discord is reserved for job notifications and source-wide outages.
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
    "android mobile",
    "ios engineer",
    "ios developer",
    "ios mobile",
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
    "asic",
    "circuit design",
    "dft engineer",
    "formal verification",
    "hardware engineer",
    "hardware tools",
    "embedded engineer",
    "embedded systems",
    "firmware engineer",
    "physical design",
    "power optimization",
    "rtl power",
    "design verification",
    "verification engineer",
    "energy modeling engineer",
    "cell modeling",
    "cell modelling",
    "electrical engineer",
    "mechanical engineer",
    "manufacturing engineer",
    "module engineer",
    # Support/Operations (not development)
    "support engineer",
    "it engineer",
    "network engineer",
    "network operations",
    "network production engineer",
    "systems engineering rotation",
    "systems administrator",
    "helpdesk",
    # Other non-SWE
    "security engineer",
    "application engineer",
    "implementation engineer",
    "integration engineer",
    "product marketing engineer",
    "technical product marketing",
    "data scientist",
    "quant research",
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

# SQLite database path. The database is a working copy; durable state is the
# JSON file passed with --state-file (committed to a state branch in CI).
DATABASE_PATH = os.environ.get(
    "JOB_TRACKER_DB",
    os.path.join(os.path.dirname(__file__), "jobs.db"),
)

# ---------------------------------------------------------------------------
# Visa sponsorship and seniority screening
# ---------------------------------------------------------------------------
# A job is dropped only when a rule below is enabled and the posting clearly
# matches it. Everything else is kept and flagged with sponsorship
# (no|unknown|yes) and seniority_flag (none|borderline|senior).
SCREENING = {
    "drop_no_sponsorship": True,
    "drop_citizenship_required": True,
    "drop_clearance_required": True,
    "drop_opt_ineligible": True,
    # Description asks for at least this many years: seniority_flag=borderline.
    "experience_flag_min_years": 2,
    # At or above this, seniority_flag=senior. Set drop_senior_experience to
    # drop those jobs instead of flagging them.
    "experience_senior_min_years": 5,
    "drop_senior_experience": False,
    # Fetch descriptions for newly found career-page jobs whose list API does
    # not include them (Greenhouse, Workday). Only new jobs are fetched.
    "fetch_descriptions": True,
    "max_description_fetches_per_run": 80,
}

# Markers used by the SimplifyJobs README legend.
LIST_MARKERS = {
    "🛂": "no_sponsorship",
    "🇺🇸": "citizenship_required",
    "🎓": "advanced_degree",
}

_NEGATION = (
    r"(?:will\s+not|won'?t|can\s*not|can'?t|do\s+not|does\s+not|don'?t|doesn'?t"
    r"|are\s+not|aren'?t|is\s+not|isn'?t|unable|not\s+able|not\s+in\s+a\s+position"
    r"|no\s+longer)"
)
# J-1 is an exchange-visitor status, so "does not support J-1 visas" says
# nothing about F-1 OPT.
_STUDENT_VISA = r"(?:F-?1|(?-i:STEM\s+OPT|OPT|CPT)|student\s+visas?)"
_STUDENT_WORK_AUTH = (
    r"(?:F-?1|(?-i:STEM\s+OPT|OPT|CPT)|(?:curricular|optional)\s+practical\s+training)"
)
_US = r"\bu\.?\s?s\.?(?:a\.?)?"

# Regular expressions are matched case-insensitively against title and
# description text. A no-sponsorship match only counts when its sentence is
# about immigration (IMMIGRATION_CONTEXT_PATTERN) and it is not sponsorship
# for an export license, so "unable to sponsor relocation costs" and "without
# sponsorship for an export license" are ignored.
IMMIGRATION_CONTEXT_PATTERN = (
    r"\b(?:visas?|h-?1b|immigration|immigrant|work\s+(?:authori[sz]ation|permits?|eligibility)"
    r"|employment\s+(?:authori[sz]ation|eligibility|sponsorship|visas?)"
    r"|authori[sz]ed\s+to\s+work|right\s+to\s+work|green\s+cards?|permanent\s+residen\w*"
    r"|citizenship|sponsorship|F-?1|(?-i:OPT|CPT)"
    r"|sponsor\w*\s+(?:candidates|applicants|individuals|employees|anyone|you|workers))\b"
)
EXPORT_LICENSE_SPONSORSHIP_PATTERN = (
    r"\bsponsor(?:ship)?\s+(?:for|of)\s+(?:an?\s+|the\s+)?(?:[\w.]+\s+){0,2}?export\b"
)

NO_SPONSORSHIP_PATTERNS = [
    _NEGATION + r"\s+(?:be\s+)?(?:able\s+)?(?:to\s+)?sponsor\b",
    r"\b(?:visa\s+|immigration\s+)?sponsorship(?:\s+available)?\s*[:?]\s*"
    r"(?:no\b|not\s+available|none\b|n/a\b|unavailable)",
    _NEGATION + r"\s+(?:be\s+)?(?:able\s+)?(?:to\s+)?"
    r"(?:offer|provide|support|sponsor|consider|accommodate|include)\w*\s+"
    r"(?:[\w/.'-]+\s+){0,5}?(?:visa|sponsor|h-?1b|immigration)",
    _NEGATION + r"\s+(?:be\s+)?(?:able\s+)?(?:to\s+)?"
    r"(?:accept|consider|hire|employ|move\s+forward\s+with)\s+(?:any\s+)?"
    r"(?:applicants?|candidates?|individuals?|anyone|persons?|people)\s+"
    r"(?:who\s+(?:will\s+|may\s+|would\s+|currently\s+|now\s+)?(?:or\s+in\s+the\s+future\s+)?"
    r"(?:require|need)s?|requiring|needing|that\s+(?:require|need)s?)\s+"
    r"(?:[\w-]+\s+){0,3}?sponsorship",
    r"\bno\s+(?:visa\s+|immigration\s+|employment\s+|h-?1b\s+)?sponsorship\b"
    r"(?!\s+(?:is\s+)?(?:required|needed|necessary))",
    r"\bsponsorship\s+(?:is\s+|will\s+)?(?:not|n't)\s+(?:be\s+)?"
    r"(?:available|offered|provided|possible|supported|an\s+option)",
    r"\bsponsorship\s+(?:is\s+)?unavailable\b",
    r"(?<!with\sor\s)\bwithout\s+(?:the\s+)?(?:need\s+(?:for|of)\s+|requiring\s+"
    r"|requirement\s+(?:for|of)\s+)?(?:(?:current\s+or\s+future|future|any)\s+)?"
    r"(?:visa\s+|employer\s+|employment\s+|immigration\s+|company\s+|h-?1b\s+)?sponsorship",
    r"\b(?:not\s+(?:be\s+)?eligible|ineligible|(?:does|do)\s+not\s+qualify)\s+for\s+"
    r"(?:visa\s+|immigration\s+|h-?1b\s+|employment\s+)?sponsorship",
    r"\b(?:must|does|do|will|should)\s+not\s+(?:now\s+or\s+in\s+the\s+future\s+)?"
    r"(?:currently\s+)?require\s+(?:[\w-]+\s+){0,2}?sponsorship",
    r"\b(?:requir(?:e|es|ing)|need(?:s|ing)?)\s+"
    r"(?:(?:now\s+or\s+in\s+the\s+future|current\s+or\s+future|future|any)\s+)?"
    r"(?:visa\s+|immigration\s+|employment\s+|employer\s+|h-?1b\s+)?"
    r"sponsorship[^.;]{0,80}?\b(?:not\s+(?:be\s+)?eligible|ineligible"
    r"|(?:will|can)\s*not\s+be\s+considered|not\s+be\s+considered)",
]

SPONSORSHIP_OFFERED_PATTERNS = [
    r"\b(?:we|company|employer|they)\s+(?:will\s+|can\s+|do\s+|does\s+|are\s+able\s+to\s+"
    r"|is\s+able\s+to\s+|happily\s+|gladly\s+)?sponsors?\s+(?:[\w-]+\s+){0,3}?"
    r"(?:visas?|h-?1b|work\s+(?:visas?|authorization)|immigration|green\s+cards?)",
    r"\b(?:visa|h-?1b|immigration)\s+sponsorship\s+(?:is\s+)?"
    r"(?:available|offered|provided|possible|supported)\b",
    r"\b(?:offers?|provides?|supports?|offering|providing)\s+"
    r"(?:visa|h-?1b|immigration|work\s+visa)\s+sponsorship\b",
    r"\bsponsorship\s+(?:is\s+)?(?:available|offered|provided)\b",
    r"\b(?:open|willing)\s+to\s+sponsor",
]

CITIZENSHIP_REQUIRED_PATTERNS = [
    _US + r"\s+citizen(?:ship)?\s+(?:is\s+|are\s+)?(?:required|mandatory|needed)",
    # Also ITAR lists: "applicant must be a (i) U.S. citizen or national, ..."
    r"\b(?:must|required\s+to|need\s+to)\s+(?:be|hold|have|possess)\s+(?:an?\s+)?"
    r"(?:\(\w{1,4}\)\s+)?" + _US + r"\s+citizen",
    r"\brequires?\s+" + _US + r"\s+citizenship\b",
    r"\b" + _US + r"\s+citizens?\s+only\b",
    r"\bonly\s+(?:open\s+to\s+)?" + _US + r"\s+citizens\b",
    r"\b(?:green\s+card|permanent\s+resident)s?\s+(?:holders?\s+)?only\b",
    r"\bmust\s+be\s+an?\s+" + _US + r"\s+person\b",
]

# Mentions that only restrict eligibility when their sentence also states a
# requirement ("restricted to US citizens or lawful permanent residents"), not
# in "U.S. citizens and permanent residents are encouraged to apply".
CITIZENSHIP_MENTION_PATTERNS = [
    r"\b(?:" + _US + r"\s+)?citizens?\s+(?:or|and|/)\s+(?:lawful\s+)?(?:" + _US
    + r"\s+)?(?:permanent\s+residents?|green\s+card\s+holders?)\b",
]

# Statements that F-1 students on OPT/CPT can be hired. One of these overrides
# a no-sponsorship, citizenship, or student-visa match in the same posting:
# "cannot sponsor H-1B, but can support OPT" leaves sponsorship unknown.
OPT_ELIGIBLE_PATTERNS = [
    r"\b(?:can|will|do|does|are\s+able\s+to|is\s+able\s+to|happy\s+to|glad\s+to|we)\s+"
    r"(?:also\s+|gladly\s+|happily\s+)?(?:support|accept|consider|hire|welcome|sponsor)\w*\s+"
    r"(?:[\w/.'()-]+\s+){0,4}?" + _STUDENT_WORK_AUTH,
    _STUDENT_WORK_AUTH + r"[^.;]{0,60}?\b(?:are|is)\s+(?:also\s+)?"
    r"(?:eligible|welcome|accepted|supported|considered)\b",
    r"\b(?:work|employment)\s+authori[sz]ation\s*[(,]?\s*(?:including|incl\.?|such\s+as|e\.g\.,?)"
    r"\s+(?:[\w-]+\s+){0,2}?" + _STUDENT_WORK_AUTH,
]

# Only applied to titles, where a bare mention implies a requirement.
TITLE_CITIZENSHIP_PATTERNS = [
    r"\b" + _US + r"\s+citizen(?:ship)?\b",
    r"\bcitizenship\s+required\b",
]

CLEARANCE_REQUIRED_PATTERNS = [
    r"\bts\s*/\s*sci\b",
    r"\btop[\s-]+secret\b",
    r"\b(?:secret|security|government|dod|federal)\s+clearance\b",
    r"\bclearance\s+(?:is\s+)?required\b",
    r"\b(?:active|current)\s+(?:ts|secret|clearance)\b",
    # Not the "Employee Polygraph Protection Act (EPPA)" poster in EEO footers.
    r"(?<!employee\s)\bpolygraph\b(?!\s+protection)",
]

OPT_INELIGIBLE_PATTERNS = [
    _STUDENT_VISA + r"[^.;]{0,60}?\b(?:not\s+(?:be\s+)?eligible|ineligible"
    r"|not\s+(?:be\s+)?(?:accepted|considered|supported)"
    r"|cannot\s+be\s+(?:accepted|considered|supported))",
    r"\b(?:not|unable\s+to|cannot|can'?t|do\s+not|does\s+not|will\s+not|won'?t)\s+"
    r"(?:accept|consider|support|hire|sponsor)\w*\s+(?:[\w/.'-]+\s+){0,4}?" + _STUDENT_VISA,
    r"\b(?:not\s+(?:be\s+)?eligible|ineligible)\b[^.;]{0,40}?" + _STUDENT_VISA,
]

# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
# Discord: at most this many jobs per run. The rest stay pending and are sent
# by later runs, oldest first. Nothing is marked delivered unless it was sent.
MAX_PENDING_JOBS_TO_NOTIFY = 50
# Pending jobs older than this are retired without being sent. None keeps
# them pending until delivered.
DISCORD_MAX_PENDING_AGE_HOURS = None

ASSISTANT_WEBHOOK_URL = os.environ.get("ASSISTANT_WEBHOOK_URL", "")
ASSISTANT_WEBHOOK_KEY = os.environ.get("ASSISTANT_WEBHOOK_KEY", "")
ASSISTANT_BATCH_SIZE = 25
ASSISTANT_MAX_JOBS_PER_RUN = 200
# Bounds the backlog sent when the assistant webhook is first configured or
# after a long outage.
ASSISTANT_MAX_PENDING_AGE_HOURS = 168
ASSISTANT_MAX_ATTEMPTS = 4
ASSISTANT_BACKOFF_SECONDS = 2.0
ASSISTANT_MAX_RETRY_AFTER_SECONDS = 60.0
ASSISTANT_TIMEOUT_SECONDS = 20

# ---------------------------------------------------------------------------
# Scheduling and durable state
# ---------------------------------------------------------------------------
# With --mode auto, the career-page scrape runs only when the last full scan
# is older than this. List repositories are checked on every run.
FULL_SCAN_INTERVAL_MINUTES = 120

# The first successful scan of a list repository or career company that has
# never been scanned is recorded without notifying when it yields more than
# this many unseen jobs. This stops newly added sources from flooding Discord.
NEW_SOURCE_BASELINE_MAX_JOBS = 5

# Delivered jobs that no source has listed for this many days are pruned from
# the state file.
STATE_RETENTION_DAYS = 180
