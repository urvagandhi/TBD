import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(
    api_key=os.environ.get("GEMINI_API_KEY"),
)

model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

response = model.generate_content(
    "Explain IEEE citation format."
)

print(response.text)
