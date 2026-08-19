# FastFlowLM

A Python orchestration client and wrapper for the **FastFlowLM (`flm`)** NPU-accelerated local inference engine (optimized for AMD Ryzen AI / Strix NPU).

`FastFlowServer` provides seamless lifecycle management for the `flm` server, OpenAI-compatible chat and completions, real-time web search and scraping tool augmentation, self-healing JSON repair, and multimodal vision & audio querying.

---

## Features

- **Automated Lifecycle Management:** Start, stop, monitor, and query `flm serve` instances directly from Python.
- **Search & Web Scraping Tools:** Augment prompts with live internet search (DuckDuckGo) and headless browser scraping (Playwright or Selenium).
- **Self-Healing JSON Generation:** Extract and automatically repair malformed JSON outputs using LLM-assisted sanitization.
- **Multimodal Support:** Single/multi-image vision analysis and audio inference.
- **OpenAI-Compatible API:** Chat completions with custom conversation history.

---

## Prerequisites

1. **FastFlowLM (`flm`) CLI:** Ensure `flm` is installed and available in your system's `PATH`.
2. **Python:** Python 3.10+ (tested up to Python 3.14).
3. **Docker (Optional):** Required only if using Selenium (`use_selenium=True`) for scraping.

---

## Installation

### Using pip

Install the required dependencies using `requirements.txt`:

```bash
pip install -r requirements.txt
```

Or install dependencies manually:

```bash
pip install requests markdownify openai ddgs playwright beautifulsoup4 selenium
```

### If using Playwright (Default Web Scraper)

Install the Chromium browser binary for Playwright:

```bash
playwright install chromium
```

### Using uv

```bash
uv sync
```

---

## Quick Start & Basic Samples

### 1. Basic Server Startup & Text Query

```python
from FastFlowLM import FastFlowServer

# Initialize server wrapper with target model
ff = FastFlowServer(model="qwen3-it:4b", port=11435)

try:
    # Start flm server (pulls model automatically if missing)
    ff.start()

    # Run a simple prompt
    response = ff.query_plain("Explain quantum computing in 2 sentences.", use_search=False)
    print("Response:\n", response)

finally:
    # Stop flm server process
    ff.stop()
```

---

### 2. Search-Augmented Querying (Live DuckDuckGo Search)

```python
from FastFlowLM import FastFlowServer

ff = FastFlowServer(model="qwen3.5:9b")

try:
    ff.start()

    # Query with live web search enabled
    answer = ff.query_plain(
        "What are the latest tech headlines today?",
        use_search=True,
        max_search_results=5
    )
    print("Answer with live search:\n", answer)

finally:
    ff.stop()
```

---

### 3. Structured JSON Output with Schema Sample

`FastFlowServer` can enforce structured JSON output and automatically repair invalid syntax.

```python
from FastFlowLM import FastFlowServer

ff = FastFlowServer(model="qwen3-it:4b")

try:
    ff.start()

    schema = {
        "city": "Amsterdam",
        "temperature_celsius": 18,
        "condition": "Partly Cloudy",
        "highlights": ["rain possible in afternoon"]
    }

    result = ff.query_plain(
        "Give me the current weather report for Paris",
        is_json=True,
        json_sample=schema,
        use_search=True
    )

    print("Parsed JSON Result:", result)
    print("City:", result.get("city"))

finally:
    ff.stop()
```

---

### 4. Multi-Turn Conversation Chat

```python
from FastFlowLM import FastFlowServer

ff = FastFlowServer(model="qwen3-it:4b")

try:
    ff.start()

    # Build conversation context
    ff.addconvo_system("You are a helpful coding assistant specialized in Python.")
    ff.addconvo_user("How do I reverse a list in Python?")
    
    reply, _ = ff.query_chat(use_search=False)
    print("Assistant:", reply)
    ff.addconvo_assistant(reply)

    # Follow-up question
    ff.addconvo_user("What is the time and space complexity?")
    reply2, _ = ff.query_chat(use_search=False)
    print("Assistant:", reply2)

finally:
    ff.stop()
```

---

### 5. Multimodal: Vision & Audio Analysis

#### Vision Analysis (Single or Multiple Images)

```python
from FastFlowLM import FastFlowServer

ff = FastFlowServer(model="qwen3.5:9b")

try:
    ff.start()

    # Single image
    _, description = ff.query_vision(
        prompt="Describe what you see in this chart.",
        image_path="chart.png"
    )
    print("Description:", description)

    # Multiple images comparison
    _, comparison = ff.query_vision_multiple(
        prompt="Compare these two images and list differences.",
        image_paths=["before.png", "after.png"]
    )
    print("Comparison:", comparison)

finally:
    ff.stop()
```

#### Audio Analysis

```python
from FastFlowLM import FastFlowServer

ff = FastFlowServer(model="gemma4-it:e4b")

try:
    ff.start()
    transcript = ff.audio(
        prompt="Transcribe and summarize this audio recording.",
        audio_path="recording.wav"
    )
    print("Transcript / Summary:", transcript)
finally:
    ff.stop()
```

---

### 6. Model Management

```python
from FastFlowLM import FastFlowServer

ff = FastFlowServer()

# List available & downloaded models
models = ff.list_models()
print("Models:", models)

# Pull a new model
ff.pull_model("qwen3-it:4b")

# Remove a model
# ff.remove_model("old-model:tag")
```

---

## Detailed Documentation

For full API documentation, all constructor parameters, method signatures, error handling, and advanced configurations, refer to **[`FastFlowLM.readme`](FastFlowLM.readme)**.
