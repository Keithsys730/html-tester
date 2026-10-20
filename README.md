# HTML Tester Agent (Standalone & Portable)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Engine-Playwright-green.svg)](https://playwright.dev/)

An autonomous, green-portable HTML testing and Multi-LLM self-healing agent.

```
┌─────────────────┐      ┌─────────────────────────┐      ┌───────────────────────┐
│  Target HTML    │ ───> │ Headless Playwright     │ ───> │ Structured Diagnostic │
│  (input/*.html) │      │  • DOM/Console Errors   │      │  • YAML Frontmatter   │
└─────────────────┘      │  • Screenshot Artifacts │      │  • Failure Captures   │
                         └─────────────────────────┘      └───────────────────────┘
                                                                      │
                                 ┌─────────────────────────┐          ▼
                                 │ Surgical Repaired HTML  │ <─── Multi-LLM Fixer
                                 │ (output/fixed/*.html)   │      (Gemini / OpenAI)
                                 └─────────────────────────┘
```

## Features

- **Green-Portable & Zero Config**: Drop onto any Windows, Linux, or macOS machine and run immediately. Auto-initializes isolated virtual environments and browser binaries.
- **Headless Browser Execution**: Uses Playwright to simulate real browsers, detecting JavaScript runtime exceptions, broken resource links, layout collisions, and unhandled promise rejections.
- **Visual Proof Screenshots**: Automatically captures high-resolution screenshots of defect points into `output/artifacts/`.
- **Closed-Loop Self-Healing (`--mode fix`)**: Feeds exact error tracebacks, DOM contexts, and screenshots to LLMs to perform minimal surgical code repairs, with automatic pre-fix backups.

## Quick Start (Zero-Configuration)

1. **Copy this folder**: Copy the entire `html-tester/` folder anywhere on any machine.
2. **Put target files**: Put your `.html` files or static project folders into `input/`.
3. **Run**:
   - **Windows**: Double-click `run.bat` (or run `run.bat` in CMD/PowerShell).
   - **Linux / macOS**: Execute `./run.sh`.
4. **Inspect Results**:
   - AI-actionable Markdown reports are generated in `output/reports/`.
   - Failure screenshots are in `output/artifacts/`.
   - Repaired files (if auto-heal mode enabled) are exported to `output/fixed/`.

---

## Directory Layout

```text
html-tester/
├── input/             # Put target .html files here
├── output/            # Generated test reports and artifacts
│   ├── reports/       # Structured Markdown reports with YAML frontmatter
│   ├── artifacts/     # Visual proof screenshots (.png)
│   └── fixed/         # Successfully repaired HTML files
├── backup/            # Automated snapshots before surgical fixes
├── core/              # Engine components (server, scanner, runner, guard, llm, fixer)
├── config.yaml        # Configuration (timeouts, budgets, model settings)
├── .env               # Optional API keys for Multi-LLM auto-healing
├── requirements.txt   # Dependencies
├── html_tester.py     # Main CLI entry point
├── run.bat            # Windows 1-click launcher with venv auto-initialization
└── run.sh             # Linux/macOS launcher
```

---

## CLI Options

```bash
# Pure diagnostic mode (default, test and report only)
python html_tester.py --mode test

# Closed-loop self-healing mode (test -> surgical fix -> verify -> export)
python html_tester.py --mode fix

# Test a specific file
python html_tester.py --target input/demo.html

# CI/CD strict mode (exits with code 1 if any target file has unresolved defects)
python html_tester.py --mode test --strict

# Run environment diagnostic check
python html_tester.py --diagnose
```

---

## How to Report Issues & Upgrade via Plain Text

If you run into any errors or crashes on another machine:
1. Open the generated `html_tester.log` (or copy the red traceback from the terminal).
2. Paste the plain text directly back into the AI assistant chat.
3. The AI assistant will diagnose the root cause and provide the patched `.py` files immediately!

---

## AI Agent Skill Integration (Claude Code / Codex / Gemini)

This repository includes a ready-to-use [SKILL.md](SKILL.md) following the standard Agent Skills specification. You can mount or copy this skill into ~/.claude/skills/html-tester/, ~/.codex/skills/html-tester/, or ~/.gemini/config/skills/html-tester/ to let your coding agents autonomously verify and self-heal HTML artifacts.
