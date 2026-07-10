# Smart Ticket Router

A local-first support ticket router built with Python, FastAPI-style service structure, Pydantic validation, and an optional Streamlit UI.

## Setup

1. Create a Python environment and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file in the project root with your configuration (see `app/config.py` for the supported keys, e.g. `OPENAI_API_KEY`, `OPENAI_MODEL`).

## Run

- CLI:
  ```bash
  python router_cli.py "I can't log into my account"
  ```
- Streamlit:
  ```bash
  streamlit run app.py
  ```

## Architecture

The routing flow uses a fast keyword-based path first and falls back to the LLM-backed service when needed.

## Notes

- The project uses environment-based configuration and avoids hardcoded secrets.
- The router returns a safe fallback when the OpenAI API is unavailable or validation fails.
