from google.genai import Client
import os
from config.settings import settings

client = Client(api_key=settings.google_api_key)
for m in client.models.list():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
