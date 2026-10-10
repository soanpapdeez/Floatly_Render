import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
print("base_url:", os.getenv("OPENAI_BASE_URL"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL") or None)
for m in client.models.list().data:
    print(m.id)