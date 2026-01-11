#!/usr/bin/env python3
"""
RSS News Digest Builder (Weekend 1 v2)
Fetches RSS feeds, filters with Claude, outputs prioritized digest.
Now with: deduplication tracking + sardonic personalized headlines + email delivery.

Run: python rss_digest.py

Environment variables needed for email:
  ANTHROPIC_API_KEY - Your Claude API key
  EMAIL_SENDER      - Your Yahoo email address
  EMAIL_PASSWORD    - Yahoo app password (not your regular password)
  EMAIL_RECIPIENT   - Where to send the digest (can be same as sender)
"""

import os
import sys
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta
from time import mktime
from pathlib import Path

# =============================================================================
# INSTALL DEPENDENCIES
# =============================================================================
def install_deps():
    import subprocess
    deps = ["feedparser", "anthropic"]
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            print(f"Installing {dep}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep, "-q"])

install_deps()

import feedparser
import anthropic

# =============================================================================
# CONFIGURATION
# =============================================================================

# Your validated feeds
FEEDS = {
    # Entertainment
    "Deadline": "https://deadline.com/feed/",
    "Deadline Legal": "https://deadline.com/category/legal/feed",
    "Variety": "https://variety.com/feed/",
    "Hollywood Reporter": "https://www.hollywoodreporter.com/feed/",
    
    # Newspapers / Magazines
    "NYT": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "LA Times": "https://www.latimes.com/news/rss2.0.xml",
    "The Atlantic": "https://www.theatlantic.com/feed/all/",
    "The Economist": "https://www.economist.com/finance-and-economics/rss.xml",
    
    # AI/Legal
    "Artificial Lawyer": "https://www.artificiallawyer.com/feed/",
    
    # Theme Parks
    "WDWNT": "https://wdwnt.com/feed/",
    "Touring Plans": "https://touringplans.com/blog/feed/",
    
    # Food & Dining
    "Eater LA": "https://la.eater.com/rss/index.xml",
    "LA Times Food": "https://www.latimes.com/food/rss2.0.xml",
}

# How far back to look (in hours)
MAX_AGE_HOURS = 24

# Tracking file for deduplication (same folder as script)
SCRIPT_DIR = Path(__file__).parent.resolve()
SEEN_FILE = SCRIPT_DIR / "seen_articles.json"

# How long to remember articles (days) - prevents file from growing forever
SEEN_RETENTION_DAYS = 7

# Model for filtering (Haiku = cheap & fast)
FILTER_MODEL = "claude-haiku-4-5-20251001"

# Model for synthesis (Sonnet = better quality)
SYNTHESIS_MODEL = "claude-sonnet-4-20250514"

# Output files for GitHub Pages
OUTPUT_HTML = SCRIPT_DIR / "index.html"
ARCHIVE_DIR = SCRIPT_DIR / "archive"

# =============================================================================
# PERSONALIZATION - THE TIRED OPENER
# =============================================================================

HEADLINES_PROMPT = """You're writing the opener for a news digest called "Iwitless Nooze."

You're not drunk, you're just tired. You've read too much news. You're making observations, not jokes.

VIBE:
- Exhausted but still paying attention
- Sardonic without trying to land a punchline
- Each bullet should convey actual information, not just vibes
- 8-12 words per bullet — enough to know what happened
- Em dashes welcome. Fragments okay. But the reader should understand the story.
- You're noting things with a sigh, not performing

IMPORTANT: Skip deaths, tragedies, and genuinely dark stories. This section is for weary corporate absurdity, not grief. If someone died, don't feature it here.

Write EXACTLY 4 bullets. No more, no less.

Format exactly:

Unfortunately—
* [tired observation about story 1]
* [sardonic note about story 2]
* [weary take on story 3]
* [resigned observation about story 4]

Examples of TOO POLISHED (don't do this):
* "Timothy Busfield proves even thirtysomething actors can't escape New Mexico jurisdiction"
* "CAA's confidential arbitration details leak faster than a Marvel plot synopsis"

Examples of TOO CRYPTIC (don't do this):
* "busfield. new mexico. the desert knows"
* "CAA appealing because losing gracefully is dead"

Examples of RIGHT ENERGY:
* "CAA appealing the Range arbitration like that ever works"
* "someone at Netflix approved 'KPop Demon Hunters Monopoly' and went home"
* "Disney painting another queue entrance— it's always painting"
* "Newsom counting AI tax revenue like it's already real money"

TODAY'S ARTICLES:
"""

# =============================================================================
# FILTERING PROMPTS BY CATEGORY
# =============================================================================

FILTER_PROMPTS = {
    "entertainment": """You are filtering entertainment industry news for a VP of Legal Affairs at a major studio who also enjoys some good industry gossip.

INCLUDE (high priority):
- M&A activity, studio acquisitions, company restructuring
- Studio/streaming leadership changes
- International co-production announcements
- Streaming distribution deals
- Labor negotiations (WGA, SAG-AFTRA, DGA, IATSE)
- Legal disputes, lawsuits, arbitration outcomes
- Regulatory/antitrust news affecting entertainment

INCLUDE (medium priority):
- Major financing deals
- International market developments
- Technology deals affecting content distribution
- Juicy actor/celebrity drama, feuds, or controversies (the good stuff)
- Industry figures saying something wild or revealing
- Talent behaving badly or speaking out
- Deaths of notable industry figures

EXCLUDE:
- Routine casting announcements (unless A-list or surprising)
- Generic reviews and criticism
- Box office numbers (unless record-breaking)
- Awards show fashion coverage
- Release date announcements (unless strategically significant)
- Puff piece interviews with nothing interesting said

For each article, respond with JSON:
{"include": true/false, "priority": "high"/"medium"/"low", "reason": "brief explanation"}""",

    "newspaper": """You are filtering general news for an entertainment industry executive in Los Angeles.

INCLUDE (high priority):
- Entertainment industry business news
- AI/tech policy and regulation
- Antitrust actions affecting media/tech
- California legislation affecting entertainment or tech
- Major corporate news about media companies

INCLUDE (medium priority):
- Significant national political developments
- Tech industry major moves
- Los Angeles local news of significance

EXCLUDE:
- Sports (unless business angle)
- Lifestyle/travel
- Opinion pieces (unless highly relevant)
- Weather
- Most crime stories
- Celebrity profiles

For each article, respond with JSON:
{"include": true/false, "priority": "high"/"medium"/"low", "reason": "brief explanation"}""",

    "ai_legal": """You are filtering AI/legal tech news for an entertainment lawyer interested in AI applications.

INCLUDE (high priority):
- AI legislation and regulation
- Copyright lawsuits involving AI
- AI in entertainment industry applications
- Contract automation tools
- Legal tech affecting deal-making

INCLUDE (medium priority):
- General AI policy developments
- Law firm AI adoption news
- AI ethics in legal context

EXCLUDE:
- Consumer AI product launches (unless legally significant)
- Technical AI research (unless policy implications)
- Generic "AI will change everything" pieces

For each article, respond with JSON:
{"include": true/false, "priority": "high"/"medium"/"low", "reason": "brief explanation"}""",

    "theme_parks": """You are filtering theme park news for someone interested in industry business and strategy.

INCLUDE (high priority):
- Corporate strategy announcements
- Capacity/expansion announcements
- Competitive moves between Disney/Universal/others
- Financial results and guidance
- Leadership changes
- New attraction openings (major ones)

INCLUDE (medium priority):
- Construction updates on major projects
- Pricing changes
- Operational changes

EXCLUDE:
- Food reviews
- Trip reports/vlogs
- Merchandise (unless significant)
- Character meet-and-greets
- Seasonal decoration coverage
- "Tips and tricks" content

For each article, respond with JSON:
{"include": true/false, "priority": "high"/"medium"/"low", "reason": "brief explanation"}""",

    "food": """You are filtering LA food and restaurant news. Be VERY permissive - this reader wants most food content.

INCLUDE (high priority):
- New restaurant openings in LA
- Restaurant closings
- Chef news and moves
- Food scene trends

INCLUDE (medium priority):
- Reviews of interesting places
- Food events
- Dining guides
- Bars WITH notable food programs
- Pretty much everything food-related in LA

EXCLUDE:
- Recipe-only content with no restaurant/scene angle
- National chain news (unless LA-specific)
- Bar news where the bar doesn't have food (reader doesn't drink, so cocktail bars, wine bars, dive bars without food = skip)

For each article, respond with JSON:
{"include": true/false, "priority": "high"/"medium"/"low", "reason": "brief explanation"}"""
}

# Map feeds to filter categories
FEED_CATEGORIES = {
    "Deadline": "entertainment",
    "Deadline Legal": "entertainment",
    "Variety": "entertainment",
    "Hollywood Reporter": "entertainment",
    "NYT": "newspaper",
    "LA Times": "newspaper",
    "The Atlantic": "newspaper",
    "The Economist": "newspaper",
    "Artificial Lawyer": "ai_legal",
    "WDWNT": "theme_parks",
    "Touring Plans": "theme_parks",
    "Eater LA": "food",
    "LA Times Food": "food",
}

# =============================================================================
# DEDUPLICATION FUNCTIONS
# =============================================================================

def get_article_hash(article):
    """Generate unique hash for an article based on title + link"""
    unique_str = f"{article.get('title', '')}{article.get('link', '')}"
    return hashlib.md5(unique_str.encode()).hexdigest()


def load_seen_articles():
    """Load previously seen article hashes"""
    print(f"  Looking for seen file at: {SEEN_FILE}")
    if SEEN_FILE.exists():
        try:
            with open(SEEN_FILE, "r") as f:
                data = json.load(f)
                # Clean old entries
                cutoff = (datetime.now() - timedelta(days=SEEN_RETENTION_DAYS)).isoformat()
                cleaned = {k: v for k, v in data.items() if v > cutoff}
                print(f"  Loaded {len(cleaned)} seen articles (cleaned from {len(data)})")
                return cleaned
        except Exception as e:
            print(f"  Error loading seen file: {e}")
            return {}
    print(f"  No seen file found, starting fresh")
    return {}


def save_seen_articles(seen):
    """Save seen article hashes with timestamps"""
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f)
    print(f"  Saved {len(seen)} seen articles to {SEEN_FILE}")


def mark_as_seen(seen, articles):
    """Add articles to seen list"""
    now = datetime.now().isoformat()
    for article in articles:
        seen[get_article_hash(article)] = now
    return seen


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_client():
    """Initialize Anthropic client"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in environment")
        print("Run: setx ANTHROPIC_API_KEY \"your-key-here\"")
        print("Then restart Command Prompt")
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def fetch_feeds(seen):
    """Fetch all RSS feeds and return NEW articles from last MAX_AGE_HOURS"""
    articles = []
    skipped_seen = 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    
    for feed_name, feed_url in FEEDS.items():
        print(f"Fetching {feed_name}...")
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries:
                # Parse date
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime.fromtimestamp(
                        mktime(entry.published_parsed), 
                        tz=timezone.utc
                    )
                
                # Skip old articles
                if pub_date and pub_date < cutoff:
                    continue
                
                # Get content
                content = ""
                if hasattr(entry, 'content') and entry.content:
                    content = entry.content[0].get('value', '')
                elif hasattr(entry, 'summary'):
                    content = entry.summary or ""
                elif hasattr(entry, 'description'):
                    content = entry.description or ""
                
                # Strip HTML
                content = re.sub('<[^<]+?>', '', content)
                content = ' '.join(content.split())
                
                article = {
                    "source": feed_name,
                    "category": FEED_CATEGORIES.get(feed_name, "entertainment"),
                    "title": entry.get('title', 'No title'),
                    "link": entry.get('link', ''),
                    "content": content[:500],  # Truncate for API efficiency
                    "date": pub_date.isoformat() if pub_date else None,
                }
                
                # Check if we've seen this before
                if get_article_hash(article) in seen:
                    skipped_seen += 1
                    continue
                    
                articles.append(article)
                
        except Exception as e:
            print(f"  Error fetching {feed_name}: {e}")
    
    print(f"\nFound {len(articles)} NEW articles ({skipped_seen} already seen)")
    return articles


def filter_article(client, article):
    """Use Claude to decide if article should be included"""
    category = article["category"]
    prompt = FILTER_PROMPTS.get(category, FILTER_PROMPTS["entertainment"])
    
    try:
        response = client.messages.create(
            model=FILTER_MODEL,
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": f"""{prompt}

ARTICLE TO EVALUATE:
Source: {article['source']}
Title: {article['title']}
Content: {article['content']}

Respond with JSON only."""
            }]
        )
        
        # Parse response
        text = response.content[0].text.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = re.sub(r'^```json?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        
        result = json.loads(text)
        return result
        
    except Exception as e:
        print(f"  Filter error for '{article['title'][:40]}...': {e}")
        return {"include": True, "priority": "medium", "reason": "Error - included by default"}


def generate_sardonic_headlines(client, filtered_articles):
    """Generate the sardonic 'Unfortunately' opener"""
    
    # Format articles for the prompt
    article_summaries = "\n".join([
        f"[{a['source']}] {a['title']} - {a['content'][:150]}..."
        for a in filtered_articles[:20]  # Cap at 20 to keep prompt reasonable
    ])
    
    try:
        response = client.messages.create(
            model=SYNTHESIS_MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": HEADLINES_PROMPT + article_summaries
            }]
        )
        return response.content[0].text.strip()
        
    except Exception as e:
        print(f"Headlines error: {e}")
        return "Unfortunately:\n* The news happened again today."


def synthesize_digest(client, filtered_articles):
    """Generate individual headline + summary for each article, grouped by category"""
    
    # Group by category for organization
    categories = {
        "entertainment": [],
        "newspaper": [],
        "ai_legal": [],
        "theme_parks": [],
        "food": []
    }
    
    for a in filtered_articles:
        cat = FEED_CATEGORIES.get(a['source'], 'newspaper')
        categories[cat].append(a)
    
    # Sort each category: high priority first, then medium
    for cat in categories:
        categories[cat].sort(key=lambda x: 0 if x.get('priority') == 'high' else 1)
    
    # Soft article limits per category (can exceed for big news)
    category_limits = {
        "newspaper": 12,
        "entertainment": 3,
        "ai_legal": 3,
        "theme_parks": 2,
        "food": 3
    }
    
    # Apply soft limits - take top N by priority
    for cat in categories:
        limit = category_limits.get(cat, 5)
        if len(categories[cat]) > limit:
            # Keep all high priority, then fill with medium up to limit
            high_priority = [a for a in categories[cat] if a.get('priority') == 'high']
            medium_priority = [a for a in categories[cat] if a.get('priority') != 'high']
            if len(high_priority) >= limit:
                categories[cat] = high_priority[:limit + 2]  # Soft limit: allow overflow for big news
            else:
                categories[cat] = high_priority + medium_priority[:limit - len(high_priority)]
    
    # Process articles in batches by category
    all_summaries = {}
    
    category_labels = {
        "newspaper": "News",
        "entertainment": "Entertainment Industry",
        "ai_legal": "AI & Legal Tech",
        "theme_parks": "Theme Parks",
        "food": "LA Food Scene"
    }
    
    for cat_key, articles in categories.items():
        if not articles:
            continue
            
        print(f"  Summarizing {len(articles)} {category_labels[cat_key]} articles...")
        
        # Format articles for batch processing
        articles_text = "\n\n---\n\n".join([
            f"ARTICLE {i+1}:\nOriginal headline: {a['title']}\nSource: {a['source']}\nContent: {a['content'][:500]}\nLink: {a['link']}"
            for i, a in enumerate(articles)
        ])
        
        target_count = category_limits.get(cat_key, 5)
        
        prompt = f"""For the articles below, create a clean digest entry for each UNIQUE story.

CRITICAL: If multiple articles cover the SAME story (e.g., same event reported by Deadline, Variety, and THR), COMBINE them into ONE entry using the best details from each. Only create separate entries if articles cover genuinely different angles or breaking developments.

Target approximately {target_count} entries for this section (fewer if stories overlap, more if genuinely distinct).

For each unique story:
1. REWRITTEN HEADLINE: Essential context, no clickbait, standalone-readable, under 15 words.
2. ONE-PARAGRAPH SUMMARY: 2-4 sentences of key facts. Direct and informative.
3. LINK: The best/most detailed source.

Format EXACTLY like this (no labels, just spacing):

**Headline goes here in bold**

Summary paragraph goes here. Two to four sentences covering key facts.

https://link.goes.here

**Next headline here**

Next summary here.

https://next.link.here

ARTICLES TO PROCESS:

{articles_text}"""

        try:
            response = client.messages.create(
                model=SYNTHESIS_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            all_summaries[cat_key] = response.content[0].text
            
        except Exception as e:
            print(f"  Summary error for {cat_key}: {e}")
            # Fallback: just use original headlines
            fallback = "\n\n".join([
                f"**{a['title']}**\n\n{a['content'][:200]}...\n\n{a['link']}"
                for i, a in enumerate(articles)
            ])
            all_summaries[cat_key] = fallback
    
    # Format final digest
    digest_parts = []
    
    # News first, then entertainment, then everything else
    category_order = ["newspaper", "entertainment", "ai_legal", "theme_parks", "food"]
    
    for cat_key in category_order:
        if cat_key in all_summaries and all_summaries[cat_key].strip():
            digest_parts.append(f"## {category_labels[cat_key]}\n\n{all_summaries[cat_key]}")
    
    return "\n\n---\n\n".join(digest_parts) if digest_parts else "No articles to summarize."


def generate_html(title, body_markdown, article_count, total_count):
    """Generate a nice HTML page for GitHub Pages."""
    
    # Convert markdown to HTML
    html_body = body_markdown
    
    # Headers
    html_body = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_body, flags=re.MULTILINE)
    
    # Bold
    html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
    
    # Links (standalone URLs on their own line)
    html_body = re.sub(r'^(https?://\S+)$', r'<a href="\1">Read more →</a>', html_body, flags=re.MULTILINE)
    
    # Bullet points  
    html_body = re.sub(r'^\* (.+)$', r'<li>\1</li>', html_body, flags=re.MULTILINE)
    
    # Wrap consecutive <li> tags in <ul>
    html_body = re.sub(r'((?:<li>.*?</li>\s*)+)', r'<ul>\1</ul>', html_body, flags=re.DOTALL)
    
    # Horizontal rules
    html_body = html_body.replace('---', '<hr>')
    
    # Line breaks (double newline = paragraph)
    html_body = re.sub(r'\n\n+', '</p>\n<p>', html_body)
    html_body = f'<p>{html_body}</p>'
    
    # Clean up empty paragraphs
    html_body = re.sub(r'<p>\s*</p>', '', html_body)
    html_body = re.sub(r'<p>\s*<h', '<h', html_body)
    html_body = re.sub(r'</h(\d)>\s*</p>', r'</h\1>', html_body)
    html_body = re.sub(r'<p>\s*<hr>\s*</p>', '<hr>', html_body)
    html_body = re.sub(r'<p>\s*<ul>', '<ul>', html_body)
    html_body = re.sub(r'</ul>\s*</p>', '</ul>', html_body)
    
    timestamp = datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')
    
    html_page = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a1a;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        h1 {{
            color: #ff6b6b;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
            font-size: 1.8em;
        }}
        h2 {{
            color: #4ecdc4;
            margin-top: 2em;
            font-size: 1.3em;
        }}
        strong {{
            color: #ffe66d;
        }}
        a {{
            color: #4ecdc4;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        hr {{
            border: none;
            border-top: 1px solid #333;
            margin: 2em 0;
        }}
        ul {{
            padding-left: 0;
            list-style: none;
        }}
        li {{
            margin: 0.5em 0;
            padding-left: 1.5em;
            position: relative;
        }}
        li:before {{
            content: "•";
            color: #ff6b6b;
            position: absolute;
            left: 0;
        }}
        .meta {{
            color: #888;
            font-size: 0.9em;
            margin-top: 3em;
            padding-top: 1em;
            border-top: 1px solid #333;
        }}
        .timestamp {{
            color: #666;
            font-size: 0.85em;
            margin-bottom: 1em;
        }}
        .unfortunately {{
            background: #252525;
            padding: 15px 20px;
            border-left: 3px solid #ff6b6b;
            margin: 1em 0 2em 0;
        }}
    </style>
</head>
<body>
    <h1>Iwitless Nooze</h1>
    <div class="timestamp">{timestamp} · <a href="archive/">Past editions</a></div>
    {html_body}
    <div class="meta">Generated from {article_count} filtered articles (of {total_count} new)</div>
</body>
</html>'''
    
    # Write to index.html
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html_page)
    
    print(f"HTML page generated: {OUTPUT_HTML}")
    
    # Archive this edition
    ARCHIVE_DIR.mkdir(exist_ok=True)
    archive_filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    archive_path = ARCHIVE_DIR / archive_filename
    with open(archive_path, 'w', encoding='utf-8') as f:
        f.write(html_page)
    print(f"Archived to: {archive_path}")
    
    # Update archive index
    update_archive_index()


def update_archive_index():
    """Generate an index page listing all archived digests"""
    
    if not ARCHIVE_DIR.exists():
        return
    
    # Get all archived HTML files, sorted newest first
    archives = sorted(ARCHIVE_DIR.glob("*.html"), reverse=True)
    archives = [a for a in archives if a.name != "index.html"]
    
    links_html = ""
    for archive in archives[:100]:  # Keep last 100
        # Parse date from filename: 20260110_1430.html
        try:
            date_str = archive.stem  # 20260110_1430
            dt = datetime.strptime(date_str, "%Y%m%d_%H%M")
            display_date = dt.strftime("%A, %B %d, %Y at %I:%M %p")
        except:
            display_date = archive.stem
        
        links_html += f'<li><a href="{archive.name}">{display_date}</a></li>\n'
    
    index_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iwitless Nooze Archive</title>
    <style>
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a1a;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        h1 {{
            color: #ff6b6b;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }}
        a {{
            color: #4ecdc4;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        ul {{
            list-style: none;
            padding: 0;
        }}
        li {{
            margin: 0.8em 0;
            padding-left: 1.5em;
            position: relative;
        }}
        li:before {{
            content: "→";
            color: #ff6b6b;
            position: absolute;
            left: 0;
        }}
        .back {{
            margin-bottom: 2em;
        }}
    </style>
</head>
<body>
    <div class="back"><a href="../">← Current edition</a></div>
    <h1>Archive</h1>
    <ul>
{links_html}
    </ul>
</body>
</html>'''
    
    with open(ARCHIVE_DIR / "index.html", 'w', encoding='utf-8') as f:
        f.write(index_html)
    
    print(f"Archive index updated with {len(archives)} editions")


def main():
    print("="*60)
    print("IWITLESS NOOZE GENERATOR")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    
    # Initialize client
    client = get_client()
    
    # Load seen articles
    seen = load_seen_articles()
    print(f"Tracking {len(seen)} previously seen articles")
    
    # Fetch feeds
    print("\n[1/4] FETCHING FEEDS...")
    articles = fetch_feeds(seen)
    
    if not articles:
        print("\nNo new articles found. You're caught up!")
        return
    
    # Filter articles
    print("\n[2/4] FILTERING WITH AI...")
    filtered = []
    
    for i, article in enumerate(articles):
        print(f"  Filtering {i+1}/{len(articles)}: {article['title'][:50]}...")
        result = filter_article(client, article)
        
        if result.get("include"):
            article["priority"] = result.get("priority", "medium")
            article["filter_reason"] = result.get("reason", "")
            filtered.append(article)
    
    print(f"\nKept {len(filtered)} of {len(articles)} articles")
    
    high_count = len([a for a in filtered if a["priority"] == "high"])
    med_count = len([a for a in filtered if a["priority"] == "medium"])
    print(f"  High priority: {high_count}")
    print(f"  Medium priority: {med_count}")
    
    # Mark ALL fetched articles as seen (not just filtered ones)
    # This prevents re-filtering rejected articles
    seen = mark_as_seen(seen, articles)
    save_seen_articles(seen)
    print(f"  Marked {len(articles)} articles as seen")
    
    if not filtered:
        print("\nNothing passed filters. Slow news day, or adjust your prompts.")
        return
    
    # Generate sardonic headlines
    print("\n[3/4] GENERATING HEADLINES...")
    headlines = generate_sardonic_headlines(client, filtered)
    
    # Synthesize digest
    print("\n[4/4] SYNTHESIZING DIGEST...")
    digest = synthesize_digest(client, filtered)
    
    if digest:
        print("\n" + "="*60)
        print("IWITLESS NOOZE")
        print("="*60 + "\n")
        
        # Print headlines first
        print(headlines)
        print("\n" + "-"*60 + "\n")
        print(digest)
        
        # Save to file
        filename = f"digest_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        full_digest = f"# Iwitless Nooze - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        full_digest += headlines
        full_digest += "\n\n---\n\n"
        full_digest += digest
        full_digest += "\n\n---\n"
        full_digest += f"*Generated from {len(filtered)} filtered articles (of {len(articles)} new)*\n"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(full_digest)
        
        print(f"\n[Saved to {filename}]")
        
        # Generate HTML for GitHub Pages
        print("\n[5/5] GENERATING HTML...")
        generate_html("Iwitless Nooze", full_digest, len(filtered), len(articles))
    else:
        print("Failed to generate digest.")


if __name__ == "__main__":
    main()
