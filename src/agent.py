"""
Regulatory Compliance Agent — Project 01
=========================================
Monitors EBA, ECB, and ESMA RSS feeds.
Claude autonomously classifies publications, creates GitHub Issues for
high-priority items, and commits a weekly compliance report.

No decision logic lives here — Claude decides when to call each tool.
"""

import os
import json
import base64
import datetime
import feedparser
import requests
import anthropic

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN      = os.environ["GITHUB_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]   # e.g. "sunday/my-fork"

MODEL             = "claude-opus-4-5"
MAX_ITERATIONS    = 60   # safety ceiling on the agentic loop
MAX_FEED_ITEMS    = 10   # cap items per feed to stay within context limits

RSS_FEEDS = {
    "EBA": "https://www.eba.europa.eu/rss/news_publications",
    "ECB": "https://www.ecb.europa.eu/rss/home.html",
    "ESMA": "https://www.esma.europa.eu/press-news/esma-news/rss",
}

# ──────────────────────────────────────────────
# Tool definitions  (the schema Claude sees)
# ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "classify_regulation",
        "description": (
            "Classify a single regulatory publication from EBA, ECB, or ESMA. "
            "Return the publication type, priority level (CRITICAL / HIGH / MEDIUM / LOW / INFORMATIONAL), "
            "affected regulatory domains, a brief summary, and recommended actions for a compliance team."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Regulatory body — one of: EBA, ECB, ESMA",
                    "enum": ["EBA", "ECB", "ESMA"],
                },
                "title": {
                    "type": "string",
                    "description": "Title of the publication as it appeared in the RSS feed",
                },
                "url": {
                    "type": "string",
                    "description": "Direct URL to the full publication",
                },
                "published": {
                    "type": "string",
                    "description": "Publication date in ISO-8601 format (YYYY-MM-DD)",
                },
                "summary": {
                    "type": "string",
                    "description": "Short description or snippet from the RSS entry",
                },
                "priority": {
                    "type": "string",
                    "description": "Assessed priority: CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL",
                    "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"],
                },
                "regulation_type": {
                    "type": "string",
                    "description": (
                        "Category: Guidelines | Regulation | Decision | Opinion | "
                        "Consultation | Report | Speech | Press Release | Other"
                    ),
                },
                "affected_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Regulatory domains impacted, e.g. "
                        "['DORA', 'CRR3', 'Basel IV', 'AML', 'MiCA', 'CSRD', 'BRRD']"
                    ),
                },
                "recommended_actions": {
                    "type": "string",
                    "description": "Concise action items for the compliance / risk team",
                },
            },
            "required": [
                "source", "title", "url", "published", "summary",
                "priority", "regulation_type", "affected_domains", "recommended_actions",
            ],
        },
    },
    {
        "name": "create_github_issue",
        "description": (
            "Open a GitHub Issue in the current repository for a high-priority regulatory item. "
            "Only call this for publications classified as CRITICAL or HIGH priority."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Issue title — include [CRITICAL] or [HIGH] prefix and the source body",
                },
                "body": {
                    "type": "string",
                    "description": "Full Markdown body for the issue (classification details, URL, actions)",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "GitHub labels to apply, e.g. ['compliance', 'eba', 'high-priority']",
                },
            },
            "required": ["title", "body", "labels"],
        },
    },
    {
        "name": "generate_compliance_report",
        "description": (
            "Commit a weekly Markdown compliance report to the repository under "
            "compliance-reports/YYYY-MM-DD.md. Call this ONCE, after all publications "
            "have been classified and all necessary issues have been created."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_date": {
                    "type": "string",
                    "description": "Report date in YYYY-MM-DD format",
                },
                "report_content": {
                    "type": "string",
                    "description": "Full Markdown content of the compliance report",
                },
                "summary_stats": {
                    "type": "object",
                    "description": "High-level counts for logging",
                    "properties": {
                        "total_items":       {"type": "integer"},
                        "critical_items":    {"type": "integer"},
                        "high_items":        {"type": "integer"},
                        "issues_created":    {"type": "integer"},
                    },
                },
            },
            "required": ["report_date", "report_content", "summary_stats"],
        },
    },
]

# ──────────────────────────────────────────────
# Feed fetching
# ──────────────────────────────────────────────

def fetch_publications() -> list[dict]:
    """Pull recent entries from all configured RSS feeds."""
    publications = []
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=7)

    for source, url in RSS_FEEDS.items():
        print(f"📡 Fetching {source} feed: {url}")
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if count >= MAX_FEED_ITEMS:
                    break
                # Parse date — feedparser gives a time_struct
                pub_date = today  # fallback
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime.date(*entry.published_parsed[:3])
                if pub_date < cutoff:
                    continue   # skip anything older than 7 days

                publications.append({
                    "source":    source,
                    "title":     entry.get("title", "No title"),
                    "url":       entry.get("link", ""),
                    "published": pub_date.isoformat(),
                    "summary":   entry.get("summary", entry.get("description", ""))[:500],
                })
                count += 1
            print(f"  ✅ {count} items collected from {source}")
        except Exception as exc:
            print(f"  ⚠️  Failed to fetch {source}: {exc}")

    print(f"\n📋 Total publications to process: {len(publications)}\n")
    return publications

# ──────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────

# In-memory store so generate_compliance_report can aggregate everything
_classified_items: list[dict] = []
_issues_created:   int = 0


def tool_classify_regulation(args: dict) -> str:
    """Store the classification result and confirm to Claude."""
    _classified_items.append(args)
    priority = args["priority"]
    source   = args["source"]
    title    = args["title"][:80]
    print(f"  🏷️  [{priority}] {source}: {title}")
    return json.dumps({
        "status":   "classified",
        "priority": priority,
        "source":   source,
        "title":    args["title"],
    })


def tool_create_github_issue(args: dict) -> str:
    """Create a real GitHub Issue via the REST API."""
    global _issues_created

    api_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title":  args["title"],
        "body":   args["body"],
        "labels": args.get("labels", []),
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        issue_data = response.json()
        issue_number = issue_data.get("number", "?")
        issue_url    = issue_data.get("html_url", "")
        _issues_created += 1
        print(f"  📌 Issue #{issue_number} created: {args['title'][:60]}")
        return json.dumps({
            "status":       "created",
            "issue_number": issue_number,
            "url":          issue_url,
        })
    except requests.HTTPError as exc:
        # 422 usually means a duplicate label — handle gracefully
        print(f"  ⚠️  GitHub Issue creation failed: {exc}")
        return json.dumps({"status": "error", "message": str(exc)})


def tool_generate_compliance_report(args: dict) -> str:
    """Commit the Markdown report to the repository."""
    report_date    = args["report_date"]
    report_content = args["report_content"]
    file_path      = f"compliance-reports/{report_date}.md"

    api_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Check if file already exists (needed for sha on update)
    sha = None
    check = requests.get(api_url, headers=headers, timeout=10)
    if check.status_code == 200:
        sha = check.json().get("sha")

    encoded_content = base64.b64encode(report_content.encode()).decode()
    payload: dict = {
        "message": f"chore: add compliance report {report_date} [skip ci]",
        "content": encoded_content,
        "branch":  "main",
    }
    if sha:
        payload["sha"] = sha

    try:
        resp = requests.put(api_url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        stats = args.get("summary_stats", {})
        print(f"\n📄 Report committed: {file_path}")
        print(f"   Total: {stats.get('total_items', '?')}  |  "
              f"Critical: {stats.get('critical_items', '?')}  |  "
              f"High: {stats.get('high_items', '?')}  |  "
              f"Issues created: {stats.get('issues_created', '?')}")
        return json.dumps({"status": "committed", "path": file_path})
    except requests.HTTPError as exc:
        print(f"  ⚠️  Failed to commit report: {exc}")
        return json.dumps({"status": "error", "message": str(exc)})


def dispatch_tool(name: str, args: dict) -> str:
    """Route a tool call from Claude to the correct implementation."""
    if name == "classify_regulation":
        return tool_classify_regulation(args)
    if name == "create_github_issue":
        return tool_create_github_issue(args)
    if name == "generate_compliance_report":
        return tool_generate_compliance_report(args)
    return json.dumps({"error": f"Unknown tool: {name}"})

# ──────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────

def build_system_prompt(publications: list[dict]) -> str:
    items_json = json.dumps(publications, indent=2)
    today      = datetime.date.today().isoformat()
    return f"""You are a senior regulatory compliance analyst AI agent at a European financial institution.

Today's date: {today}

## Your Task
You have been given {len(publications)} regulatory publications collected from EBA, ECB, and ESMA RSS feeds this week.

Process them in this exact order:
1. Call `classify_regulation` for EVERY publication — no exceptions.
2. For each publication classified as CRITICAL or HIGH priority, immediately call `create_github_issue` with a clear, actionable issue body.
3. After ALL publications are classified and ALL issues created, call `generate_compliance_report` exactly once with a full Markdown summary report.

## Priority Guidelines
- CRITICAL: Immediate regulatory deadlines, mandatory implementation within 3 months, systemic risk warnings
- HIGH: Important guidelines/regulations with 3–12 month implementation windows, DORA/Basel IV/MiCA updates
- MEDIUM: Consultations open for comment, speeches with policy signals, supervisory expectations
- LOW: Research reports, statistics, non-binding opinions
- INFORMATIONAL: Press releases, event announcements, staff papers

## GitHub Issue Format
Title: `[PRIORITY] SOURCE: Publication Title — YYYY-MM-DD`
Body must include:
- **Source**: EBA / ECB / ESMA
- **Type**: Regulation type
- **Published**: Date
- **Link**: URL
- **Domains affected**: list
- **Summary**: 2–3 sentences
- **Recommended Actions**: bullet list for compliance team
- **Deadline / Implementation Date**: if known

## Compliance Report Format
Use clear Markdown with:
- Executive summary (total counts, key themes)
- Table of all CRITICAL and HIGH items
- Full list of all processed items with priority
- Recommended next steps

## Publications to Process
```json
{items_json}
```

Begin processing now. Work through every publication systematically.
"""

# ──────────────────────────────────────────────
# Agentic loop
# ──────────────────────────────────────────────

def run_agent():
    print("=" * 60)
    print("🤖 Regulatory Compliance Agent — Starting")
    print("=" * 60)

    publications = fetch_publications()

    if not publications:
        print("ℹ️  No new publications found this week. Exiting.")
        return

    client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": build_system_prompt(publications)}]
    iteration = 0

    print("\n🔄 Starting agentic loop...\n")

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"── Iteration {iteration} ──────────────────────────────")

        response = client.messages.create(
            model      = MODEL,
            max_tokens = 4096,
            tools      = TOOLS,
            messages   = messages,
        )

        print(f"   stop_reason: {response.stop_reason}")

        # ── Claude is done ──
        if response.stop_reason == "end_turn":
            print("\n✅ Claude finished. Agentic loop complete.")
            # Print any final text from Claude
            for block in response.content:
                if hasattr(block, "text"):
                    print("\n📝 Claude's final message:\n")
                    print(block.text)
            break

        # ── Claude wants to call tools ──
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"   🔧 Tool call: {block.name}({list(block.input.keys())})")
                    result = dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

            # Append assistant turn then tool results
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",      "content": tool_results})

        else:
            # Unexpected stop reason — log and exit
            print(f"⚠️  Unexpected stop_reason: {response.stop_reason}. Exiting loop.")
            break

    else:
        print(f"\n⚠️  Safety ceiling reached ({MAX_ITERATIONS} iterations). Stopping.")

    # ── Final summary ──
    print("\n" + "=" * 60)
    print("📊 Run Summary")
    print("=" * 60)
    print(f"  Publications processed : {len(_classified_items)}")
    print(f"  GitHub Issues created  : {_issues_created}")
    print(f"  Iterations used        : {iteration}")

    # Priority breakdown
    from collections import Counter
    priority_counts = Counter(item["priority"] for item in _classified_items)
    for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"]:
        count = priority_counts.get(priority, 0)
        if count:
            print(f"  {priority:<15}: {count}")

    print("=" * 60)


if __name__ == "__main__":
    run_agent()
