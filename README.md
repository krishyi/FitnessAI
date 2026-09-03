# 🥗 Fitness AI

<img width="802" height="930" alt="image" src="https://github.com/user-attachments/assets/d6067929-9d6d-4cb7-bef2-c7d03b4b8b19" />

<img width="782" height="1025" alt="image" src="https://github.com/user-attachments/assets/c2857c3a-45f5-4694-867b-1f3a2d7ef728" />

<img width="757" height="1031" alt="image" src="https://github.com/user-attachments/assets/02b3d58e-47eb-49b9-9668-ea315b724f35" />

Log a meal in plain English and get calorie tracking, general fitness
advice, and BMI insights — powered by a local LLM (Ollama) and real
nutrition databases, not AI guesswork.

## Features
- Natural language meal logging ("2 eggs, a bowl of rice, and grilled chicken")
- Calorie data pulled from USDA FoodData Central + Open Food Facts,
  cross-checked for plausibility - never a raw LLM-invented number
- Clearly labeled confidence levels per item (verified database match,
  typical-size estimate, or last-resort AI estimate)
- BMI calculation + general fitness/diet Q&A
- Metric/imperial unit toggle

## Tech Stack
FastAPI · Ollama (mistral) · USDA FoodData Central API · Open Food Facts API · Vanilla JS/HTML/CSS

## Why this architecture
Early versions asked the LLM to recall calorie values directly - it
sounded confident but was frequently wrong. This version restructures
that: Ollama is used only for what LLMs are actually good at (parsing
messy text into structured food items, disambiguating between real
database candidates, generating general advice) - it never invents a
calorie number. All calorie data comes from USDA or Open Food Facts,
cross-checked against a plausibility range, with a full fallback chain
before ever reaching an explicitly-labeled AI estimate.

## Setup
1. Clone the repo, `cd` into it
2. `python -m venv venv` then activate it
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`, add a free USDA key from
   api.data.gov/signup
5. Install Ollama, run `ollama pull mistral`
6. Terminal 1: `py -m uvicorn main:app --reload --port 8000`
7. Terminal 2 (inside `frontend/`): `python -m http.server 5500`
8. Visit `http://localhost:5500` — **Ollama must be running locally**
   for meal analysis and advice generation to work

## Limitations
- Meal history is in-memory and resets when the backend restarts
- Requires Ollama running locally
