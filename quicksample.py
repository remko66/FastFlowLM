"""Quick sample script demonstrating key features of FastFlowLM.

Includes:
- Basic plain text querying
- Search-augmented structured JSON querying
- Webpage downloading and summarization
"""
from FastFlowLM import FastFlowServer

def sample_basic_query(server: FastFlowServer) -> str:
    """Run a simple, direct plain text query without search."""
    print("\n--- 1. Basic Query Sample ---")
    prompt = "Who was Albert Einstein in 2 sentences?"
    print(f"Prompt: {prompt}")

    response = server.query_plain(prompt, use_search=False)
    print("Response:\n", response)
    return response


def sample_structured_weather_query(server: FastFlowServer) -> dict:
    """Run a search-augmented query requesting structured JSON output with a template."""
    print("\n--- 2. Structured JSON Query with Live Search ---")

    user_query = "What is the weather forecast for Amsterdam?"

    # Define the desired JSON structure/schema template
    json_template = {
        "date": "date of tomorrow",
        "url-info": "https://www.nu.nl/weer",
        "weather": {
            "condition": "Mostly Sunny",
            "temperature_high_celsius": 23,
            "temperature_low_celsius": 11,
            "description": "The weather forecast for Amsterdam is predicted to be mostly sunny.",
        },
    }

    print(f"Query: {user_query}")
    print("Querying NPU with search augmentation and JSON output...")

    result = server.query_plain(
        prompt=user_query,
        is_json=True,
        use_search=True,
        max_search_results=20,
        json_sample=json_template,
    )

    print("Parsed JSON Result:\n", result)
    return result


def sample_scrape_and_summarize(server: FastFlowServer, url: str) -> str:
    """Download content from a URL and summarize the extracted text.

    Requires Playwright (or Selenium container if use_selenium=True).
    """
    print(f"\n--- 3. Web Scraping & Summarization for: {url} ---")

    print("Downloading webpage content...")
    page_data = server.download_url(url)
    page_text = page_data.get("text", "")
    print(f"Downloaded {len(page_text)} characters of text.")

    # Summarize extracted text
    summary_prompt = f"Make a concise summary of the following text:\n\n{page_text[:4000]}"
    print("Generating summary...")
    summary = server.query_plain(summary_prompt, use_search=False)

    print("Summary:\n", summary)
    return summary


def main():
    """Initialize FastFlowServer, manage lifecycle, and run all samples."""
    # Initialize FastFlowServer instance
    ff_server = FastFlowServer(model="qwen3.5:9b")

    try:
        # 1. Start the FastFlowLM server background process
        print("Starting FastFlowLM server...")
        ff_server.start()

        # 2. Run basic plain query
        sample_basic_query(ff_server)

        # 3. Run structured JSON search query
        weather_data = sample_structured_weather_query(ff_server)

        # 4. Scrape the source URL returned from weather data and summarize it
        if isinstance(weather_data, dict) and "url-info" in weather_data:
            target_url = weather_data["url-info"]
            sample_scrape_and_summarize(ff_server, target_url)

    finally:
        # Ensure the server process is properly terminated even if an error occurs
        print("\nStopping FastFlowLM server...")
        ff_server.stop()


if __name__ == "__main__":
    main()