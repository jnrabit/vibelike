#!/usr/bin/env python3
import os
import sys

print("VOR load_dotenv:")
print(f"  GEMINI_API_KEY: {os.environ.get('GEMINI_API_KEY', 'NOT SET')[:30]}...")

from dotenv import load_dotenv
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, '.env')
print(f"\nLading .env from: {_env_path}")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
    print("✓ .env loaded")
else:
    print("✗ .env not found")

print(f"\nNACH load_dotenv:")
print(f"  GEMINI_API_KEY: {os.environ.get('GEMINI_API_KEY', 'NOT SET')[:30]}...")

# Test ob es funktioniert
import google.genai as genai
from google.genai import types

try:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Hi",
        config=types.GenerateContentConfig(max_output_tokens=50)
    )
    print(f"\n✅ Gemini works!")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"\n❌ Error: {str(e)[:100]}")
