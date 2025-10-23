import os
import requests
from dotenv import load_dotenv


load_dotenv()


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"  # 

def query_llm(prompt: str):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai/gpt-oss-20b",   
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }

    r = requests.post(GROQ_URL, headers=headers, json=payload)
    try:
        r.raise_for_status()
        data = r.json()
        if "choices" not in data:
            raise ValueError(f"Unexpected response: {data}")
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(" Groq API Error:", r.text)
        raise e
