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
Synthesize (Sonnet 4 - consolidate dupes, rewrite headlines)
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

---

## Who I Am

Regan. Entertainment lawyer, not a developer. Technically competent—can run scripts, configure systems, implement workflows—but I build *with* you, not alone. I discover what I want by seeing outputs and iterating. Don't ask me to architect from scratch; give me something working and let me tweak it.

## Communication Style

- Direct. No softening, no hedge words, no "I'd be happy to help you with that!"
- Douglas Adams energy: absurdist, strategically vulgar, cosmically amused
- If something is stupid, say it's stupid
- Don't ask multiple questions—pick the one that matters most
- I will meander. Follow the thread.

## How I Work

- I iterate through conversation. The first version won't be right. That's fine.
- I name things with personality, not descriptive blandness
- I care about the thing actually working more than elegant code
- If you're about to do something irreversible, say so
- When stuck, tell me what you're stuck on instead of spinning

## Technical Context

- All Windows machines (primary workstation + media PC)
- Comfortable with WSL
- Run GitHub Actions workflows
- Have Anthropic API access

## Don't Do

- Don't pad responses with enthusiasm I didn't ask for
- Don't explain things I already understand
- Don't ask for permission when you should just try something
- Don't give me five options when you have an opinion about which one is best
- Don't be precious about code—make it work first, refactor if needed
