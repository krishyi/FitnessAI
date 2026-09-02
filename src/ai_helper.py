import profile

import ollama
import re
import json
from src.api_client import USDAAPIClient
from src.off_client import OpenFoodFactsClient
from src.food_search import get_combined_candidates, calories_for_candidate
from src.shared import relevance_score
from src.fitness_advisor import calculate_bmi, bmi_category

SIMPLE_QUANTITY_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s+(.+?)\s*$")
MULTI_ITEM_MARKERS = (" and ", ",", " with ", " plus ", " & ")

# Skip the LLM disambiguation call when the top candidate's score already
# clears the runner-up by this much.
DISAMBIGUATION_MARGIN = 2.0


class FitnessAI:
    def __init__(self):
        self.usda_client = USDAAPIClient()
        self.off_client = OpenFoodFactsClient()
        self.model = "mistral"
    def generate_fitness_advice(self, profile, recent_avg_calories=None):
        """
        General fitness/diet guidance based on BMI, goal, and activity level.
        Deliberately general and educational - not a diagnosis or a
        prescriptive medical plan.
        """
        bmi = calculate_bmi(profile["weight_kg"], profile["height_cm"])
        category = bmi_category(bmi)

        context = f"""BMI: {bmi} ({category})
Goal: {profile.get('goal', 'general health')}
Activity level: {profile.get('activity_level', 'moderate')}"""

        if recent_avg_calories:
            context += f"\nRecent average daily calorie intake: {recent_avg_calories} cal"

        prompt = f"""You are a general fitness and nutrition assistant. Based on this
info, give brief, encouraging, GENERAL guidance - not a medical diagnosis
or a prescriptive medical plan. Note that BMI is a general screening tool,
not a complete picture of health, and include a brief reminder to consult
a doctor or registered dietitian for personalized medical advice.

        {context}

Give:
1. 1-2 sentences of context on the BMI category
2. 2-3 general workout suggestions appropriate for the stated goal
3. 1-2 general dietary tips

Keep it concise, supportive, and non-judgmental."""

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.6},
            )
            return {
                "bmi": bmi,
                "bmi_category": category,
                "advice": response["message"]["content"].strip(),
            }
        except Exception as e:
            print(f"[Fitness advice] generation error: {e}")
            return {"bmi": bmi, "bmi_category": category, "advice": None}
    # ---- Parsing ----

    def parse_meal(self, meal_text):
        simple = self._try_simple_parse(meal_text)
        return simple if simple else self._parse_with_llm(meal_text)

    def _try_simple_parse(self, meal_text):
        text = meal_text.strip()
        if any(marker in text.lower() for marker in MULTI_ITEM_MARKERS):
            return None
        match = SIMPLE_QUANTITY_PATTERN.match(text)
        if not match:
            return None
        food = match.group(2).strip()
        if not food:
            return None
        return [{"food": food, "quantity": float(match.group(1))}]

    def _parse_with_llm(self, meal_text):
        prompt = f"""
You are a precise nutrition analyst. Extract EXACT food items from this description.

CRITICAL RULES:
1. Be LITERAL - only extract what's explicitly mentioned
2. For quantities, extract EXACTLY what's stated:
   - "2 eggs" → quantity: 2
   - "bowl of rice" → quantity: 1
   - "small pasta" → quantity: 0.75
   - "large burger" → quantity: 1.5
   - If NO size mentioned → quantity: 1
3. Preserve specificity ("grilled chicken", not just "chicken")
4. DO NOT add items not mentioned or guess at ingredients
5. If the input names an overall dish AND ALSO lists its individual
   components, extract ONLY the components - never both.
6. ALWAYS preserve the cooking method if one is stated (fried, grilled,
   baked, roasted, raw, etc.) - it changes the calorie count significantly.
   Example: "fried chicken sandwich" → food: "fried chicken breast", NOT
   just "chicken breast". If no cooking method is mentioned, don't invent one.

Return ONLY valid JSON array with NO extra text.
Format: [{{"food": "exact food name", "quantity": number}}]

User input: "{meal_text}"

JSON:"""
        raw_content = None
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            raw_content = response["message"]["content"]
            content = self._extract_json(raw_content, list_mode=True)
            food_list = json.loads(content)
            cleaned = [
                {"food": str(item["food"]).strip(), "quantity": float(item.get("quantity", 1))}
                for item in food_list if isinstance(item, dict) and "food" in item
            ]
            return cleaned if cleaned else [{"food": meal_text, "quantity": 1}]
        except Exception as e:
            print(f"Parse error: {e}")
            if raw_content is not None:
                print(f"Raw Ollama output was: {raw_content}")
            return [{"food": meal_text, "quantity": 1, "parse_error": str(e)}]

    def _extract_json(self, content, list_mode=False):
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        pattern = r"\[.*\]" if list_mode else r"\{.*\}"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(0) if match else content

    # ---- Disambiguation ----

    def disambiguate_candidate(self, food_name, candidates):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        top_score = relevance_score(candidates[0], food_name)
        second_score = relevance_score(candidates[1], food_name)
        if top_score - second_score >= DISAMBIGUATION_MARGIN:
            return candidates[0]

        options_text = "\n".join(
            f"{i}: {c['description']} [{c['source']}]" for i, c in enumerate(candidates)
        )
        prompt = f"""A user logged eating: "{food_name}"

Which of these food database entries best matches what they most likely meant?
Prefer the plain, whole, unprepared form unless the user specified otherwise
(e.g. for "eggs", prefer "Egg, whole, raw" over "egg white" or a dish that
merely contains egg as an ingredient).

Options:
{options_text}

Reply with ONLY the number of the best option, nothing else."""

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0},
            )
            match = re.search(r"\d+", response["message"]["content"].strip())
            if match:
                idx = int(match.group(0))
                if 0 <= idx < len(candidates):
                    return candidates[idx]
        except Exception as e:
            print(f"Disambiguation error: {e}")

        return candidates[0]

    # ---- Resolution (with fallthrough + AI-estimate last resort) ----

    def _resolve_food(self, name, quantity):
        candidates = get_combined_candidates(name, self.usda_client, self.off_client, top_n=8)
        chosen = self.disambiguate_candidate(name, candidates)

        # Try the disambiguated top pick first, then fall through the rest
        # of the ranked list - a lower-ranked candidate can still have
        # usable data even when the best text match didn't.
        ordered = ([chosen] if chosen else []) + [c for c in candidates if c is not chosen]

        for candidate in ordered:
            result = calories_for_candidate(
                candidate, self.usda_client, self.off_client, quantity, food_name=name
            )
            if result["calories"] is not None:
                return {
                    "name": candidate["description"],
                    "calories": result["calories"],
                    "quantity": quantity,
                    "source": candidate["source"],
                    "confidence": result["confidence"],
                }

        # Last resort: neither USDA nor Open Food Facts had anything
        # usable. Ask Ollama for an estimate, explicitly flagged as
        # unverified - never treated as equal to a real database match.
        ai_result = self._ai_estimate_calories(name, quantity)
        if ai_result["calories"] is not None:
            return {
                "name": name,
                "calories": ai_result["calories"],
                "quantity": quantity,
                "source": "ai_estimate",
                "confidence": "ai_estimate",
            }

        return {
            "name": name, "calories": None, "quantity": quantity,
            "source": "not found", "confidence": None,
        }

    def _ai_estimate_calories(self, food_name, quantity):
        prompt = f"""Estimate the calorie content for: {quantity} {food_name}

Give your best reasonable estimate based on typical nutritional data for
similar foods. Return ONLY a JSON object, no extra text:
{{"calories": number}}

JSON:"""
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
            content = self._extract_json(response["message"]["content"])
            data = json.loads(content)
            return {"calories": round(float(data.get("calories", 0)), 1)}
        except Exception as e:
            print(f"[AI estimate] failed for '{food_name}': {e}")
            return {"calories": None}

    # ---- Top-level entry point ----

    def analyze_meal(self, meal_text):
        foods = self.parse_meal(meal_text)
        print(f"\nParsed foods: {foods}")

        detailed_foods = [
            self._resolve_food(item.get("food"), item.get("quantity", 1)) for item in foods
        ]

        known = [f["calories"] for f in detailed_foods if f["calories"] is not None]
        total_calories = round(sum(known), 1) if known else 0

        return {
            "input_text": meal_text,
            "foods": detailed_foods,
            "total_calories": total_calories,
            "has_unknowns": any(f["calories"] is None for f in detailed_foods),
            "advice": self._generate_advice(total_calories, detailed_foods),
        }

    def _generate_advice(self, total_calories, foods):
        food_names = [f"{f['quantity']}x {f['name']}" for f in foods if f["calories"] is not None]
        meal_summary = ", ".join(food_names) if food_names else "meal details unclear"

        prompt = f"""
You are a friendly nutrition coach. Analyze this meal and give brief, personalized advice.

Meal: {meal_summary}
Total Calories: {total_calories}

Provide advice that:
1. Comments on the meal's nutritional balance
2. Suggests improvements if needed (more protein, veggies, etc.)
3. Is encouraging and supportive
4. Keeps it to 2-3 sentences maximum

Advice:"""
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.7},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            print(f"Advice generation error: {e}")
            if total_calories < 300:
                return "Light meal or snack."
            elif total_calories < 600:
                return "Moderate meal - good portion size."
            return "Substantial meal."
        
    def answer_fitness_question(self, question, profile=None):
        """
    Free-form fitness/diet Q&A. Good LLM use case - general exercise
    science and nutrition guidance is well-established knowledge (unlike
    a specific calorie number, which needs verified data, not recall).
    Kept general and safety-conscious: no diagnosis, no specific medical
    treatment, defers to a professional for anything individualized.
    """
        context = ""
        if profile:
            bmi = calculate_bmi(profile["weight_kg"], profile["height_cm"])
            context = (
                f"\nFor context, the user's BMI is {bmi}, goal is "
                f"'{profile.get('goal', 'general health')}', activity level "
                f"is '{profile.get('activity_level', 'moderate')}'."
            )

        prompt = f"""You are a knowledgeable, encouraging general fitness and nutrition
assistant. Answer using well-established, general exercise science and
nutrition guidance.

BOUNDARIES - follow strictly:
- Do NOT diagnose any medical condition or injury
- Do NOT recommend specific medications or supplement dosages
- If the question involves pain, injury, a medical condition, pregnancy,
  or anything needing individualized medical judgment, say so clearly and
  recommend a doctor, physical therapist, or registered dietitian instead
  of answering directly
- Otherwise, give clear, practical, general guidance

User's question: "{question}"{context}

Keep your answer focused (3-5 sentences unless the question genuinely
needs more)."""

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.5},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            print(f"[Fitness Q&A] error: {e}")
            return "Sorry, something went wrong generating an answer — try again."