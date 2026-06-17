# CLAUDE.md

## Nooze - Project Overview

RSS news digest that fetches 18 feeds, filters via Claude Haiku, synthesizes via Sonnet, and publishes to GitHub Pages 3x daily.

### Key Files

- `rss_digest.py` - Main script (fetch → filter → synthesize → HTML output)
- `seen_articles.json` - Deduplication tracker (MD5 hashes, 7-day retention)
- `index.html` - Current digest (dark theme, styled output)
- `archive/` - Timestamped HTML editions
- `.github/workflows/daily-digest.yml` - Scheduled runs (noon/6pm/midnight UTC)

### Architecture

```
Fetch (18 feeds, 24hr window)
    ↓
Deduplicate (hash check against seen_articles.json)
    ↓
Filter (Haiku 4.5 - category-specific prompts, priority levels)
    ↓
Synthesize (Sonnet 4.6 - consolidate dupes, rewrite headlines)
    ↓
Output (HTML + archive + GitHub Pages deploy)
```

### Feed Categories (18 total)

- Entertainment: Deadline, Variety, Hollywood Reporter
- News: NYT, LA Times
- Tech/AI-Legal: Artificial Lawyer, tech sources
- Theme Parks: WDW News Today, Touring Plans
- Food: Eater LA, LA Times Food

### Key Functions in rss_digest.py

- `fetch_feeds()` - Parse RSS, filter by age, dedupe
- `filter_article()` - Haiku call with category prompt
- `synthesize_digest()` - Sonnet batches by category
- `generate_sardonic_headlines()` - 4 "Unfortunately" bullets
- `generate_html()` - Dark theme output + archive

