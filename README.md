# Job Tracker

Automated job tracker for new grad software engineering positions. Sends Discord alerts hourly via GitHub Actions.

## Monitored Companies

**Big Tech:** Google, Meta, Amazon, Apple, Netflix, Microsoft, Stripe, Block

**Cloud & Infrastructure:** Cloudflare, HashiCorp, Datadog, Confluent, CockroachLabs, PlanetScale, Temporal, Snowflake

**Developer Tools:** GitHub, GitLab, Vercel, Netlify, Supabase, Linear, Replit

**Seattle:** Expedia, Zillow, F5

**Startups:** Airbnb, Rubrik, Fly.io, Railway, Render

## Setup

1. Add `DISCORD_WEBHOOK_URL` to GitHub repository secrets
2. Edit `config.py` to customize companies
3. Runs hourly automatically, or trigger manually from Actions tab

## Commands

```bash
python main.py              # Check for jobs
python main.py --notify     # Check and send Discord alerts
python main.py --stats      # View statistics
```
