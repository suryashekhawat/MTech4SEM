# Slide Deck — How to Export

Source file: **`presentation.md`** (Marp format, 12 slides, ~15 min)

## Option 1 — VS Code / Cursor (recommended)

1. Install the **Marp for VS Code** extension (`marp-team.marp-vscode`)
2. Open `project-report/presentation.md`
3. Click the Marp icon → **Export Slide Deck**
4. Choose **PDF** or **PPTX** (PowerPoint)

## Option 2 — Marp CLI

```bash
npm install -g @marp-team/marp-cli
cd project-report
marp presentation.md --pdf -o MTech4SEM_review.pdf
marp presentation.md --pptx -o MTech4SEM_review.pptx
```

## Option 3 — Paste into Google Slides / PowerPoint

Each `---` in `presentation.md` separates one slide. Copy slide sections manually if you prefer native slides.

## Slide map (timing guide)

| Slide | Topic | ~Time |
|-------|--------|-------|
| 1 | Title | 0:30 |
| 2 | Problem | 1:30 |
| 3 | Objectives | 1:00 |
| 4 | Dataset & pipeline | 1:00 |
| 5 | Architecture | 1:00 |
| 6 | Point-in-time snapshots ⭐ | 2:00 |
| 7 | Inference stack | 1:30 |
| 8 | Airflow DAGs | 1:00 |
| 9 | Critical Patient Brief | 1:00 |
| 10 | Dashboard demo | 1:30 |
| 11 | Feedback overlay ⭐ | 1:30 |
| 12 | Evaluation & conclusion | 1:30 |

⭐ = emphasize for reviewers

## Demo backup

If live Streamlit fails, use screenshots in `project-report/screenshots/` (already embedded in slides 5, 9, 10, 11).

## Optional swap

On slide 5, replace `01_pipeline_setup.png` with `system_architecture.png` if you prefer the architecture diagram over the sidebar screenshot.
