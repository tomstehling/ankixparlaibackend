# Local Development & Hosting Guide

This guide explains how to set up and run the AnkiXParlaI backend on your local machine.

## 🏗️ 1. Environment Setup

1.  **Navigate to the backend directory:**
    ```bash
    cd ankixparlaibackend
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## 🔑 2. Configuration (.env)

The application uses a `.env` file for configuration. **Crucially, by default, local development connects to the hosted Supabase database.**

### Connecting to the Hosted Supabase Database (Default)
To use the remote Supabase instance while developing locally, ensure your `.env` has these variables set:

```env
# This flag tells the app to use the Supabase URL instead of localhost
CONNECT_LOCALLY_TO_SUPABASE="true"

# The IPv4 pooler URL for Supabase (required for many local ISP environments)
SUPABASE_DATABASE_URL_IPV4='postgresql+asyncpg://...'

# Other required keys
OPENROUTER_API_KEY='your_key_here'
```

### Connecting to a Local Postgres Instance
If you want to run a truly local database (e.g., via Docker or a local Postgres install):
1.  **Comment out** or remove the `CONNECT_LOCALLY_TO_SUPABASE` line.
2.  Ensure your `DB_USER`, `DB_PASSWORD`, `DB_SERVER`, `DB_PORT`, and `DB_NAME` variables are correctly configured.

## 🚀 3. Running the Server

Start the FastAPI server using Uvicorn:

```bash
python main.py
```

*Note: The `main.py` script is configured to automatically use the host, port, and reload settings defined in your `.env` or `core/config.py`.*

## 🩺 4. Verification

Once started, you can verify the server is running by visiting:
*   **Health Check:** `http://localhost:8000/`
*   **API Documentation (Swagger):** `http://localhost:8000/docs`
*   **Interactive ReDoc:** `http://localhost:8000/redoc`

## ⚠️ Common Issues

*   **Port already in use:** If you see `[Errno 48] Address already in use`, kill the process using port 8000:
    ```bash
    lsof -ti :8000 | xargs kill -9
    ```
*   **Missing Prompts:** If the server fails to start due to a `FileNotFoundError` in `system_prompts/`, ensure all required `.txt` files exist in that directory.
