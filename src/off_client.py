from itertools import product
import re
import time
import requests

from src.shared import is_plausible_density, lookup_known_weight

class OpenFoodFactsClient:
    """
    Free, crowd-sourced, no signup required. Strongest on packaged/branded
    grocery products; weaker on raw whole foods and restaurant items, which
    is why it runs ALONGSIDE USDA rather than replacing it.
    """
    BASE_URL = "https://world.openfoodfacts.org/cgi/search.pl"
    HEADERS = {"User-Agent": "EatrieFitnessAI - Student Project - Python"}

    def raw_search(self, food_name, page_size=10, retries=2):
        """
        OFF's free legacy endpoint occasionally returns transient 5xx
        errors under load. Retry briefly before giving up - a single
        server hiccup shouldn't force a fall-through to the AI-estimate
        tier when a normal retry would return real data.
        """
        last_error = None

        for attempt in range(retries + 1):
            try:
                response = requests.get(
                    self.BASE_URL,
                    params={
                        "search_terms": food_name,
                        "search_simple": 1,
                        "action": "process",
                        "json": 1,
                        "page_size": page_size,
                        "sort_by": "unique_scans_n",
                    },
                    headers=self.HEADERS,
                    timeout=10,
                )
                response.raise_for_status()
                return response.json().get("products", [])

            except requests.exceptions.HTTPError as e:
                last_error = e
                status = e.response.status_code if e.response is not None else None
                if status and 500 <= status < 600 and attempt < retries:
                    wait = 0.5 * (attempt + 1)
                    print(f"[OFF] {status} on attempt {attempt + 1}, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                break

            except Exception as e:
                last_error = e
                break

        print(f"[OFF] search failed for '{food_name}' after retries: {last_error}")
        return []

    def calories_for_product(self, product, quantity=1, food_name=None):
        nutriments = product.get("nutriments", {})
        per_100g = nutriments.get("energy-kcal_100g")

        per_serving = nutriments.get("energy-kcal_serving")
        if per_serving is not None:
            if per_100g is not None and not is_plausible_density(per_100g):
                print(f"[plausibility] rejecting OFF product, bad density: {per_100g} kcal/100g")
                return {"calories": None, "confidence": None}
            return {"calories": round(per_serving * quantity, 1), "confidence": "off_label_serving"}

        if not is_plausible_density(per_100g):
            if per_100g is not None:
                print(f"[plausibility] rejecting OFF product, bad density: {per_100g} kcal/100g")
            return {"calories": None, "confidence": None}

        serving_grams = self._parse_serving_grams(product)
        confidence = "off_serving_size"

        if serving_grams is None and food_name:
            serving_grams = lookup_known_weight(food_name)
            if serving_grams:
                confidence = "table"

        if serving_grams is None:
            return {"calories": round(per_100g * quantity, 1), "confidence": "fallback_100g"}

        calories_per_serving = (per_100g / 100) * serving_grams
        return {"calories": round(calories_per_serving * quantity, 1), "confidence": confidence}

    def _parse_serving_grams(self, product):
        serving_quantity = product.get("serving_quantity")
        if serving_quantity:
            try:
                return float(serving_quantity)
            except (TypeError, ValueError):
                pass

        serving_size = product.get("serving_size", "") or ""
        match = re.search(r"([\d.]+)\s*g\b", serving_size)
        return float(match.group(1)) if match else None