# silent-failure-demo

A booking agent where tools return 200 OK but deliver bad data. Instrumented with [Progress Observability](https://observability.progress.com) to show how traces catch failures that traditional monitoring misses.

Run it 20–30 times to generate a mix of healthy and broken traces, then explore them at https://observability.progress.com.

---

## Quick start

```bash
pip install progress-observability langchain-openai python-dotenv httpx certifi
python silent_failure_demo.py
```

Copy `.env.example` to `.env` and fill in your keys:

| Variable | Description |
|---|---|
| `OBSERVABILITY_APP_NAME` | App name shown in Progress Observability |
| `OBSERVABILITY_API_KEY` | API key from https://observability.progress.com |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `OPENWEATHERMAP_API_KEY` | OpenWeatherMap API key (used by weather tool) |

Set `NO_FAILURES=1` to force all tools to return healthy data (useful to generate a baseline trace).

---

## Running alongside Fiddler Everywhere

[Fiddler Everywhere](https://www.telerik.com/fiddler/fiddler-everywhere) lets you inspect every HTTP/S request the agent makes — OpenAI completions, OTLP trace exports, everything — without changing a line of agent logic.

### Why it's useful

- See the exact JSON sent to and received from `api.openai.com` for each LLM call.
- Inspect OTLP payloads going to `collector.observability.progress.com`.
- Use the **Agent Inspector** tab (see below) to view per-call token counts and cost breakdowns without leaving Fiddler.

### Setup

**1. Enable network traffic capture in Fiddler Everywhere**

Open Fiddler Everywhere and start a capture session. You can use either:
- **System Proxy** mode (toggle on in the top toolbar) — Fiddler registers itself as the system proxy; most apps route through it automatically.
- **Network capturing** mode — captures at the OS network level; useful when apps ignore the system proxy.

**2. Trust Fiddler's root CA in the Python app**

Because Fiddler performs TLS interception it presents its own certificate. Python's HTTP clients (`httpx`, `urllib3`, gRPC) use the `certifi` CA bundle by default, which does not include Fiddler's CA — so you'll get `SSLCertVerificationError` without this step.

Export Fiddler's root certificate as a PEM file:

> **Fiddler Everywhere** → Settings → HTTPS → *Export CA Certificate* → save as `FiddlerRoot.pem`

Then add the path to your `.env`:

```dotenv
FIDDLER_CA_CERT=C:/Users/you/Desktop/FiddlerRoot.pem
```

The app will merge this certificate with the `certifi` bundle at startup and apply it to:
- `httpx` (OpenAI API calls)
- `urllib3` / `requests` (via `REQUESTS_CA_BUNDLE`)
- the OpenTelemetry gRPC exporter (via `OTEL_EXPORTER_OTLP_CERTIFICATE`)

No SSL verification is disabled — all other connections continue to be verified normally.

**3. Run the agent**

```bash
python silent_failure_demo.py
```

You will see requests appear in the Fiddler **Live Traffic** list:
- `https://api.openai.com/v1/chat/completions` — the LLM call
- `https://collector.observability.progress.com/v1/tr…` — OTLP trace batches

---

## Comparing AI cost views: Progress Observability vs Fiddler Agent Inspector

Both tools surface token and cost data, but from different vantage points.

### Progress Observability

Go to https://observability.progress.com after running the agent. Each trace shows:
- The full span tree: agent → workflow → tools → LLM call
- Token counts and cost per LLM span
- The **actual prompt and completion text** (when `trace_content=True`)
- A filterable signal for silent failures: traces where `status = success` but `all_valid = false`

This is the right view for understanding *why* a run failed — what data the LLM actually received, which tool returned bad results, and how the failure propagated.

### Fiddler Everywhere — Agent Inspector

Click any `https://api.openai.com/v1/chat/completions` session in Fiddler's Live Traffic list, then open the **Agent Inspector** tab. You'll see:

| Sub-tab | What it shows |
|---|---|
| **Cost** | Input tokens, output tokens, total tokens, input cost, output cost, total cost |
| **Latency** | Time-to-first-token and total response time |
| **Messages** | The raw messages array (system prompt, user turn, assistant reply) |
| **Model** | Model name and parameters |

This is the right view for real-time, per-request inspection — especially useful during development to sanity-check prompts, spot unexpectedly large payloads, or verify that the model and parameters are what you expect before you have enough runs to look at traces.

### At a glance

| | Progress Observability | Fiddler Agent Inspector |
|---|---|---|
| Scope | Full agent trace across all spans | Single HTTP request |
| Best for | Post-run analysis, silent failure detection | Real-time prompt/response inspection |
| Token & cost data | Yes, per span | Yes, per request |
| Prompt content | Yes (with `trace_content=True`) | Yes (Messages tab) |
| Silent failure detection | Yes (span attributes + filtering) | No |
| No code changes needed | SDK instrumentation required | No — pure network capture |

