# AnkiXParlaI - AI-Powered Spanish Learning Backend

AnkiXParlaI Backend is a robust, high-performance API designed to power an intelligent Spanish language learning ecosystem. It orchestrates complex interactions between **Large Language Models (LLMs)**, a custom **Spaced Repetition System (SRS)**, and a sophisticated pedagogical database.

Built with Python and FastAPI, this backend demonstrates advanced patterns in asynchronous programming, database design, and AI integration.

## 🚀 Key Features (Technical Highlights)

*   **🧠 Spanish Learning Intelligent Engine:** A complex data model managing hierarchical relationships between grammatical tags, learning "hacks" (mnemonics/rules), and verb lemmas. It tracks user performance at a granular level to provide personalized learning paths.
*   **🤖 Multi-Provider LLM Orchestration:** Seamlessly integrates with **Google Gemini** and **OpenRouter** (GPT models) to handle conversational practice, automated grammar correction, and dynamic flashcard generation.
*   **📈 FSRS Spaced Repetition Logic:** Implements the **Free Spaced Repetition Scheduler (FSRS)** algorithm to calculate optimal review intervals, moving beyond traditional Anki-style SM-2 algorithms for superior retention.
*   **⚡ High-Performance Asynchronous API:** Built on **FastAPI** using `async`/`await` patterns for non-blocking I/O, ensuring the application remains responsive during heavy LLM processing.
*   **🏗️ Advanced ORM & Database Design:** Utilizes **SQLAlchemy 2.0** with **PostgreSQL** (via Supabase). Features complex many-to-many relationships, JSONB storage for flexible metadata, and Alembic for robust schema migrations.
*   **🔐 Secure JWT Authentication:** Implements OAuth2 with Password Flow and JWT tokens for secure user sessions and resource protection.

## 🛠️ Tech Stack

*   **Language:** [Python 3.11+](https://www.python.org/)
*   **Framework:** [FastAPI](https://fastapi.tiangolo.com/)
*   **ORM:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async)
*   **Database:** [PostgreSQL](https://www.postgresql.org/) (Supabase)
*   **AI Integration:** Google Generative AI (Gemini), OpenAI SDK (via OpenRouter)
*   **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
*   **Authentication:** Passlib (bcrypt), PyJWT, Python-Multipart

## 📁 Project Structure

*   `routers/`: Domain-driven API endpoints (Chat, Cards, Auth, Feedback).
*   `services/`: Core business logic layers, including `llm_handler.py` and `fsrs_handler.py`.
*   `database/`: SQLAlchemy models, async session management, and seeding scripts.
*   `system_prompts/`: Version-controlled AI instructions for specialized pedagogical tasks.
*   `core/`: Centralized configuration and security settings.

## 🏁 Getting Started

### Prerequisites
*   Python 3.11+
*   PostgreSQL database (or SQLite for local testing)

### Installation
1.  Clone the repository.
2.  Create and activate a virtual environment:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Configure environment variables:
    Create a `.env` file based on the provided template (request template if missing).
5.  Run the application:
    ```bash
    uvicorn main:app --reload
    ```

---

*This backend is the core of the AnkiXParlaI Fullstack suite.*
