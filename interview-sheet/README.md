# Interview Sheet

Local YAML/JSON-driven interview form that opens in your browser, collects answers, and exits.

## Quick start

```bash
python interview-sheet/interview_sheet.py --in interview-sheet/sample.questions.yaml
```

This opens a local page, downloads a copy of the answers, saves answers to `sample.questions.answers.json`, and exits after submit.

## Questions YAML format

```yaml
title: Indicator spec interview
description: |
  Short context, **bold**, `inline code`, ==highlight==, and lists are supported:
  - Item one
  - Item two
questions:
  - id: placement_label
    type: choice
    label: Placement + label
    prompt: >
      When you say **existing top bar**, do you mean the main toolbar?
    options:
      - Main toolbar
      - Secondary toolbar
      - Another area
    allow_none: true
    none_label: None of the choices
    allow_text: true
    text_label: Elaboration (optional)
    required: true
  - id: tooltip_ux
    type: text
    label: Tooltip UX
    prompt: Is a native title tooltip acceptable, or do you want a small hover card?
    text_label: Answer
    required: false
final_note:
  enabled: true
  label: Anything else to add?
  prompt: Optional extra context or follow-ups.
```

JSON is also supported for `--in` if you prefer.

### Supported question fields

- `id` (string, required)
- `type` (string, required): `choice` or `text`
- `label` (string, optional)
- `prompt` (string, optional, supports basic markdown)
- `required` (bool, optional)

For `choice` questions only:

- `options` (list of strings)
- `allow_none` (bool, optional)
- `none_label` (string, optional)
- `allow_text` (bool, optional)
- `text_label` (string, optional)
- `text_placeholder` (string, optional)
- `min` / `max` (int, optional)

For `text` questions only:

- `text_label` (string, optional)
- `text_placeholder` (string, optional)

### Markdown support

- Bold: `**text**`
- Inline code: `` `code` ``
- Highlight: `==text==`
- Lists: `- item` or `1. item`
- Code blocks: triple backticks

## Output format

The script writes a JSON file like:

```json
{
  "title": "Indicator spec interview",
  "description": "...",
  "source": "/abs/path/to/sample.questions.yaml",
  "submitted_at": "2026-01-24T00:00:00+00:00",
  "answers": [
    {
      "id": "placement_label",
      "type": "choice",
      "label": "Placement + label",
      "response": {
        "type": "choice",
        "selected": ["Main toolbar"],
        "none_selected": false,
        "text": "Add detail"
      }
    }
  ],
  "final_note": "Optional extra context"
}
```

On submit, the browser also downloads a copy named like (using the input file stem):

```
yyyymmdd_hhmmss_filename.answers.json
```

## CLI options

- `--in` (required): questions YAML/JSON
- `--out` (optional): answers JSON (default: same name with `.answers.json`)
- `--host` (default: `127.0.0.1`)
- `--port` (default: `0` for random free port)
- `--no-open` (optional): do not open a browser window

## YAML dependency

YAML input uses PyYAML. Install once:

```bash
pip install pyyaml
```
