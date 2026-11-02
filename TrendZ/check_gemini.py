
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env")

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

response = client.models.generate_content(
    model=model,
    contents=(
        "You are a beauty marketing analyst. "
        "Explain in two sentences how a brand can "
        "evaluate an emerging skincare trend."
    ),
)

print("Model:", model)
print("\nGemini response:")
print(response.text)
