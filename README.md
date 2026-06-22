# Automated Job Search & Daily Email Digest

A self-running job search assistant that scrapes multiple job boards every morning based on a set of defined criteria, filters results by location, scores them by relevance, and delivers a clean summary email — so you wake up to a curated list of new listings, not a pile of browser tabs.

---

## What it does

- Searches for new jobs matching your criteria across multiple sources
- Filters by location (set to UK jobs and EU-friendly remote roles by default)
- Scores each listing by relevance (★ to ★★★★★) and puts the best matches at the top
- Translates any non-English descriptions automatically
- Tracks what it has already sent you — so you only ever see **new** listings
- Emails you a formatted digest every morning at 8am
- Runs entirely on GitHub — no computer needs to be on

---

## Job sources

| Source | Type |
|--------|------|
| LinkedIn | Scraped via JobSpy |
| Glassdoor | Scraped via JobSpy |
| Google Jobs | Scraped via JobSpy |
| Indeed | Scraped via JobSpy |
| Remotive | Free public API |
| The Muse | Free public API |
| Arbeitnow | Free public API |
| Jobicy | Public RSS feed |

---

## Want to use this yourself?

Feel free to fork this repo and adapt the search criteria to your own needs. To get it running you will need to set up a few things on your end:

### 1. Fork the repo
Click **Fork** at the top right of this page to create your own copy.

### 2. Update the search criteria
Open `job_scraper.py` and edit the keyword lists near the top (`TIER1`, `TIER2`, `TIER3`) to match the roles you are looking for.

### 3. Set up a Gmail App Password
The digest is sent via Gmail SMTP. You will need:
- A Google account with **2-Step Verification** enabled
- A **Gmail App Password** — generate one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

### 4. Add GitHub Secrets
In your forked repo go to **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|-------------|-------|
| `GMAIL_USERNAME` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | The 16-character app password from Step 3 |

### 5. Update the recipient email
In `.github/workflows/job_scraper.yml`, change the `to:` field under **Send email** to your own email address.

### 6. Enable Actions
Go to the **Actions** tab in your forked repo and enable workflows. The digest will then run automatically every morning. You can also trigger a manual run any time from that tab to test it.

---

## Schedule

Runs daily at **7am UTC** (8am UK summer time / BST). Adjust the cron line in `.github/workflows/job_scraper.yml` if you want a different time.
