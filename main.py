# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date
from src.ai_helper import FitnessAI

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)

ai = FitnessAI()

meal_log = []

class MealInput(BaseModel):
    text: str

@app.get("/")
def root():
    return {"status": "Backend running"}

@app.post("/analyze-meal")
def analyze_meal(meal: MealInput):
    result = ai.analyze_meal(meal.text)
    result["date"] = str(date.today())
    meal_log.append(result)
    return result

@app.get("/today")
def get_today():
    today = str(date.today())
    todays_meals = [m for m in meal_log if m["date"] == today]
    total = sum(m["total_calories"] for m in todays_meals)
    return {"meals": todays_meals, "total_calories": total}

@app.get("/history")
def get_history():
    return {"meals": meal_log}

class ProfileInput(BaseModel):
    weight_kg: float
    height_cm: float
    goal: str = "general health"
    activity_level: str = "moderate"

@app.post("/fitness-advice")
def fitness_advice(profile: ProfileInput):
    recent_avg = None
    if meal_log:
        recent_entries = meal_log[-7:]  # crude "last week" proxy
        recent_avg = round(sum(m["total_calories"] for m in recent_entries) / len(recent_entries), 1)

    return ai.generate_fitness_advice(profile.dict(), recent_avg_calories=recent_avg)

class FitnessQuestion(BaseModel):
    question: str
    weight_kg: float | None = None
    height_cm: float | None = None
    goal: str | None = None
    activity_level: str | None = None

@app.post("/fitness-chat")
def fitness_chat(q: FitnessQuestion):
    profile = None
    if q.weight_kg and q.height_cm:
        profile = {
            "weight_kg": q.weight_kg,
            "height_cm": q.height_cm,
            "goal": q.goal or "general health",
            "activity_level": q.activity_level or "moderate",
        }
    return {"question": q.question, "answer": ai.answer_fitness_question(q.question, profile)}