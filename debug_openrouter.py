import asyncio
import os
from dotenv import load_dotenv
import openai

# Load environment variables with override to ensure we get the correct values
load_dotenv(".env", override=True)

async def debug_openrouter():
    """Debug OpenRouter API connection."""

    api_key = os.getenv("OPENROUTER_API_KEY")

    print("=" * 60)
    print("OPENROUTER API KEY DEBUG")
    print("=" * 60)

    if not api_key:
        print("❌ ERROR: OPENROUTER_API_KEY not found in environment")
        return

    print(f"✓ API Key found: {api_key[:15]}...{api_key[-4:]}")
    print(f"✓ API Key length: {len(api_key)} characters")

    # Clean the key
    api_key = api_key.strip("'").strip('"')
    print(f"✓ API Key cleaned: {api_key[:15]}...{api_key[-4:]}")

    model_name = os.getenv("OPENROUTER_MODEL_NAME", "openai/gpt-oss-120b:free")
    print(f"✓ Model name: {model_name}")

    try:
        print("\n🔍 Attempting to initialize OpenRouter client...")
        client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://ankixparlai.com",
                "X-Title": "AnkiXParlaI",
            },
        )
        print("✓ Client initialized successfully")

        print("\n🔍 Testing simple API call...")
        response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Say 'Hello!'"}],
        )

        print("✓ API call successful!")
        print(f"✓ Response: {response.choices[0].message.content}")
        print(f"✓ Model used: {response.model}")
        print(f"✓ Usage: {response.usage}")

    except openai.AuthenticationError as e:
        print(f"\n❌ AUTHENTICATION ERROR:")
        print(f"   Status: {e.status_code}")
        print(f"   Message: {e.message}")
        print(f"   This usually means the API key is invalid or expired.")

    except openai.APIError as e:
        print(f"\n❌ API ERROR:")
        print(f"   Status: {getattr(e, 'status_code', 'N/A')}")
        print(f"   Message: {e.message}")
        print(f"   Code: {getattr(e, 'code', 'N/A')}")

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR:")
        print(f"   {type(e).__name__}: {e}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(debug_openrouter())
