---
name: html-tester
description: Autonomous, zero-config portable HTML testing and Multi-LLM self-healing agent powered by Playwright. Use when testing static HTML files, capturing DOM/console runtime errors, generating visual defect screenshots, or running closed-loop surgical HTML/JS auto-repair.
argument-hint: "[--mode test|fix] [--target path/to/file.html] [--strict]"
disable-model-invocation: false
compatibility: "Windows / Linux / macOS | Python 3.10+ | Playwright"
---

# HTML Tester — Portable HTML Testing & Self-Healing Skill

## Purpose

`html-tester` provides deterministic headless browser verification and optional Multi-LLM surgical repair for static `.html` / `.htm` files.

## Execution Workflow

1. **Environment Diagnostic Check**:
   ```bash
   python html_tester.py --diagnose
   ```
2. **Diagnostic Test Mode (Read-Only Verification)**:
   ```bash
   python html_tester.py --mode test --target input/demo_broken.html
   ```
   - Inspects all interactive elements (`button`, `a`, `input`, `select`).
   - Captures unhandled JS exceptions, resource 404s, and visual proof screenshots in `output/artifacts/`.
   - Emits a structured Markdown report with YAML frontmatter in `output/reports/`.
3. **CI/CD Strict Gate Mode**:
   ```bash
   python html_tester.py --mode test --strict
   ```
   - Exits with non-zero code (`1`) if any unresolved defect is detected.
4. **Closed-Loop Self-Healing Mode**:
   ```bash
   python html_tester.py --mode fix --target input/demo_broken.html
   ```
   - Automatically snapshots the original file to `backup/`, applies surgical LLM repairs, re-verifies in headless Chromium, and exports green files to `output/fixed/` (or rolls back if still failing).

## Iron Rules (不可違反之鐵律)

1. **Repro Before Fix (先復現後修復)**：不可在未執行 `--mode test` 取得確定性失敗報告前直接盲改目標 HTML。
2. **Backup & Rollback Integrity (備份與回滾完整性)**：在 `--mode fix` 下若自動修復未能使測試全數轉綠，系統強制回滾至 `backup/` 原始狀態，不可留存半壞狀態之檔案。
3. **Outbound Network Isolation (外連網路沙盒隔離)**：測試期間由 `NetworkGuard` 攔截非本機之未知外部請求，防止測試過程觸發外部副作用。

## Validation Command (機械驗證指令)

```bash
pytest tests -q
```
