# project-01-regulatory-compliance-agent
# 🏦 Project 01 — Regulatory Compliance Agent

> **Category A: GitHub Actions + AI API** — runs entirely in GitHub's cloud. No local setup needed.

An autonomous AI agent that monitors **EBA**, **ECB**, and **ESMA** RSS feeds every Monday, classifies each publication using Claude's Tool Use (function calling), opens GitHub Issues for high-priority items, and commits a weekly Markdown compliance report — all without you writing a single line of decision logic.

---

## 🤖 Why It's Agentic

Most automation scripts are deterministic: *if condition → do action*. This agent is different.

Claude is given a set of tools and a goal. It then **decides for itself**:
- Which publications are high-priority vs. informational
- Whether to create a GitHub Issue for a specific item
- When it has processed everything and can stop

You write the tools. Claude writes the logic. That's the agentic loop.

```
┌─────────────────────────────────────────────────────┐
│                   AGENTIC LOOP                      │
│                                                     │
│  1. Feed Claude the RSS publications + tools        │
│  2. Claude calls classify_regulation(...)           │
│  3. If HIGH priority → Claude calls                 │
│       create_github_issue(...)                      │
│  4. Repeat for every publication                    │
│  5. Claude calls generate_compliance_report(...)    │
│  6. Claude returns end_turn → loop exits            │
└─────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
project-01-regulatory-compliance-agent/
├── README.md
├── requirements.txt
├── src/
│   └── agent.py                    ← All agentic logic lives here
└── .github/
    └── workflows/
        └── compliance-agent.yml    ← Scheduled GitHub Actions workflow
```

---

## ⚙️ Step-by-Step Setup

### 1. Fork this repository
Click **Fork** at the top-right of the GitHub page.

### 2. Add your Anthropic API key as a secret

1. Go to your fork → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your key from [console.anthropic.com](https://console.anthropic.com)

### 3. Add a GitHub token with write permissions

The agent needs to create Issues and push files. GitHub Actions provides
`GITHUB_TOKEN` automatically — **no extra setup needed**. The workflow already
references it.

### 4. Enable GitHub Actions

Go to the **Actions** tab of your fork → click **"I understand my workflows, enable them"**.

### 5. Run manually (first time)

1. Actions tab → **🤖 Regulatory Compliance Agent**
2. Click **Run workflow** → **Run workflow** (green button)
3. Expand the run logs — you'll see Claude calling tools in real time

After the first manual run, the agent runs automatically **every Monday at 07:00 UTC**.

---

## 🛠️ Tools Available to Claude

| Tool | Description | When Claude uses it |
|------|-------------|---------------------|
| `classify_regulation` | Classifies a publication by type, priority, and affected domains | For every RSS item |
| `create_github_issue` | Opens a GitHub Issue with labels and body text | When priority is HIGH or CRITICAL |
| `generate_compliance_report` | Commits a Markdown report to the repo | Once, after all items are processed |

---

## 📊 Output Example

**GitHub Issue (auto-created by Claude):**
```
Title: [HIGH] EBA: Guidelines on DORA ICT Risk Management — 2025-04-28
Labels: compliance, eba, high-priority, ict-risk
Body: Classification summary + link + recommended actions
```

**Committed report:** `compliance-reports/YYYY-MM-DD.md`
```markdown
# Weekly Compliance Report — 2025-04-28
## Summary
- 12 publications processed
- 3 HIGH priority items → Issues created
- 9 INFORMATIONAL items → logged only
...
```

---

## 🔍 Key Code Concept — The Agentic Loop

```python
while iteration < max_iterations:
    response = client.messages.create(tools=tools, messages=messages)

    if response.stop_reason == "end_turn":
        break  # Claude decided it's done

    if response.stop_reason == "tool_use":
        # Claude wants to call a tool — we don't decide which one
        for block in response.content:
            if block.type == "tool_use":
                result = dispatch_tool(block.name, block.input)
                # Feed the result back so Claude can continue reasoning
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                ]})
```

The critical insight: **you never write `if priority == "HIGH": create_issue()`**.
Claude makes that call based on its classification output and the instructions in the system prompt.

---

## 🔗 Resources

- [Anthropic Tool Use Docs](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [EBA RSS Feeds](https://www.eba.europa.eu/rss)
- [ECB Publications RSS](https://www.ecb.europa.eu/rss/home.html)
- [ESMA News RSS](https://www.esma.europa.eu/press-news/rss)
- [GitHub Actions Docs](https://docs.github.com/en/actions)

---

## 📄 License

MIT — free to fork, adapt, and deploy in your own compliance workflows.
