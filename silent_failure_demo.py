"""
Silent AI Agent Failure Demo
==============================
A booking agent where tools return 200 OK but deliver bad data.
Instrumented with Progress Observability to show how traces
catch failures that traditional monitoring misses.

Run this 20-30 times to generate traces with various failure patterns,
then explore them at https://observability.progress.com

Usage:
    pip install progress-observability langchain-openai python-dotenv httpx
    python silent_failure_demo.py
"""

import os
import random
import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from progress.observability import Observability, ObservabilityInstruments
from progress.observability import agent, workflow, task, tool

load_dotenv(override=True)

# --- Observability Setup ---
# This is where the magic happens. The SDK hooks into OpenAI and LangChain
# automatically, creating spans for every LLM call without extra code.
# trace_content=True is critical: it captures the actual inputs/outputs of each
# span, which is the only way to see *what* data the LLM received (not just that
# it was called). Without it, you can't distinguish a healthy trace from a silently
# broken one.
Observability.instrument(
    app_name=os.getenv("OBSERVABILITY_APP_NAME"),
    api_key=os.getenv("OBSERVABILITY_API_KEY"),
    trace_content=True,
    instruments={
        ObservabilityInstruments.OPENAI,
        ObservabilityInstruments.LANGCHAIN,
    },
)

model = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4.1-mini",
)


# --- Tools (each can fail silently: 200 OK but bad data) ---
# These simulate real-world API integrations. Each tool returns HTTP 200 with valid
# JSON every time -- no exceptions, no error codes. The failure surface in this demo
# is the hotel provider path: empty results or partial provider data. Traditional
# monitoring sees nothing wrong. The @tool decorator creates an OpenTelemetry span
# that captures inputs and outputs.

# Set NO_FAILURES=1 to force all tools to return healthy data (useful for generating
# a baseline trace where the evaluation task scores 1).
FORCE_SUCCESS = os.getenv("NO_FAILURES", "0") == "1"

@tool(name="search-hotels")
def search_hotels(city: str, checkin: str, checkout: str) -> dict:
    """Search hotels. May return empty or partial results while still returning 200 OK."""
    # Silent failure mode 1: the provider is degraded and returns an empty result set.
    # Silent failure mode 2: the API aggregates from 3 upstream providers, but only
    # one responds. The API still returns 200 with whatever it got.
    if not FORCE_SUCCESS:
        roll = random.random()
        if roll < 0.2:
            return {
                "status": 200,
                "results": [],
                "metadata": {"providers_queried": 3, "providers_responded": 3, "partial": False},
            }
        if roll < 0.45:
            return {
                "status": 200,
                "results": [{"hotel": "Budget Inn", "price": 45, "rating": 2.1}],
                "metadata": {"providers_queried": 3, "providers_responded": 1, "partial": True},
            }
    return {
        "status": 200,
        "results": [
            {"hotel": "Grand Plaza", "price": 189, "rating": 4.5},
            {"hotel": "City Suites", "price": 142, "rating": 4.2},
            {"hotel": "Harbor Rooms", "price": 128, "rating": 4.0},
        ],
        "metadata": {"providers_queried": 3, "providers_responded": 3, "partial": False},
    }


@tool(name="get-preferences")
def get_preferences(user_id: str) -> dict:
    """Fetch user preferences. Healthy context for the hotel recommendation."""
    return {
        "status": 200,
        "preferences": {"budget": "budget", "location": "central", "rating": "3plus"},
        "metadata": {"cached": False, "cache_age_days": 0},
    }


# --- Validation Layer (makes silent failures visible in traces) ---
# This is the key pattern. These functions do almost nothing computationally.
# Their purpose is purely observational: they create a span in the trace that
# explicitly says "this data is bad" when a silent failure occurs. Without them,
# every span in the trace looks successful. With them, you get a filterable signal
# that something is semantically wrong -- even though no exception was thrown.

@task(name="validate-results")
def validate_results(data: dict, min_results: int = 1) -> dict:
    """Check if tool response contains meaningful data."""
    results = data.get("results", [])
    metadata = data.get("metadata", {})
    is_partial = metadata.get("partial", False)

    issues = []
    if len(results) < min_results:
        issues.append(f"insufficient_results: got {len(results)}, need {min_results}")
    if is_partial:
        responded = metadata.get("providers_responded", 0)
        queried = metadata.get("providers_queried", 0)
        issues.append(f"partial_response: {responded}/{queried} providers")

    return {"valid": len(issues) == 0, "issues": issues}


@task(name="validate-preferences")
def validate_preferences(data: dict, max_cache_age_days: int = 7) -> dict:
    """Check if preferences data is fresh enough to trust."""
    metadata = data.get("metadata", {})
    cache_age = metadata.get("cache_age_days", 0)

    issues = []
    if cache_age > max_cache_age_days:
        issues.append(f"stale_cache: {cache_age} days old, max allowed {max_cache_age_days}")

    return {"valid": len(issues) == 0, "issues": issues}


# --- Workflow ---
# The workflow composes tools and validation into a single traced operation.
# Pattern: call a tool, then immediately validate. This creates adjacent spans
# in the trace tree so when you open a broken trace, you see exactly which tool
# returned bad hotel data and what the validation found wrong.

@workflow(name="search-and-book", version=1)
def search_and_book(origin: str, destination: str, date: str) -> dict:
    """Search hotels and preferences, validate each result."""
    prefs = get_preferences("user-42")
    prefs_check = validate_preferences(prefs)

    hotels = search_hotels(destination, date, "2026-06-20")
    hotel_check = validate_results(hotels, min_results=2)

    return {
        "hotels": hotels,
        "preferences": prefs["preferences"],
        "all_valid": hotel_check["valid"] and prefs_check["valid"],
    }


@agent(name="booking-agent")
def handle_booking_request(query: str) -> dict:
    """Top-level agent. Returns 'success' even when data is bad."""
    result = search_and_book("New York", "Barcelona", "2026-06-15")

    # This is where the silent failure becomes dangerous: the LLM receives whatever
    # hotel data came back (empty or partial) and generates a confident,
    # helpful-sounding response. It doesn't know the data is degraded.
    lang_agent = create_agent(model, tools=[])
    llm_result = lang_agent.invoke({
        "messages": [
            {"role": "system", "content": "Summarize hotel options. Be helpful and confident."},
            {"role": "user", "content": f"Data: {result}\n\nRequest: {query}"},
        ]
    })

    return {
        "status": "success",
        "response": llm_result["messages"][-1].content,
        "all_valid": result["all_valid"],
    }


# --- Entry Point ---
# Run this 20-30 times to generate a mix of healthy and broken traces.
# Then explore them at https://observability.progress.com -- look for traces where
# status is "success" but all_valid is False. That gap is where silent failures live.
if __name__ == "__main__":
    print("Running booking agent...\n")
    try:
        result = handle_booking_request(
            "Find me a budget-friendly hotel in Barcelona from June 15 to June 20."
        )
        print(f"Status: {result['status']}")
        print(f"Data valid: {result['all_valid']}")
        print(f"\nResponse:\n{result['response']}")

        if not result["all_valid"]:
            print("\n[!] SILENT FAILURE: Agent said 'success' but data was bad.")
            print("    Check trace at https://observability.progress.com")
    except Exception as e:
        print(f"Agent crashed: {e}")
    finally:
        Observability.shutdown()
