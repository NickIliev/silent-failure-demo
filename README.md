# Silent Failure Demo

This repository contains a Python demo app that simulates a travel booking AI agent with **silent failures**:

- tools often return `200 OK`
- but the returned data may be empty or partial
- the top-level agent can still report `"status": "success"`

The app is instrumented with **Progress Observability** so you can inspect traces and spot data-quality failures that normal uptime/error monitoring can miss.

## What the demo does

The script (`silent_failure_demo.py`) performs a simple booking flow:

1. searches flights (sometimes returns empty results with 200)
2. searches hotels (sometimes returns partial provider data with 200)
3. validates tool results
4. asks an LLM to summarize options
5. returns success even when validation shows bad data

Run the app multiple times to produce different failure patterns, then inspect traces in Progress Observability.

## Prerequisites

- Python 3.10+
- An OpenAI API key
- A Progress Observability API key

## Setup

1. Clone this repository and move into it.
2. (Recommended) Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   pip install progress-observability langchain-openai python-dotenv httpx
   ```

4. Create a `.env` file in the project root:

   ```env
   OPENAI_API_KEY=your_openai_key
   OBSERVABILITY_API_KEY=your_progress_observability_key
   ```

## Run the demo

```bash
python silent_failure_demo.py
```

Run it 20–30 times to generate a useful sample of trace outcomes.

Optional loop command:

```bash
for i in {1..25}; do python silent_failure_demo.py; done
```

## Expected output

Each run prints:

- `Status` (typically `success`)
- `Data valid` (`True` or `False`)
- an LLM-generated travel summary

When `Data valid: False`, the app flags a silent failure and points you to:

https://observability.progress.com

## Troubleshooting

- **Missing API keys**: verify `.env` contains both `OPENAI_API_KEY` and `OBSERVABILITY_API_KEY`.
- **Import errors**: reinstall dependencies in the active environment.
- **No visible failures yet**: rerun several times; failures are randomized by design.
