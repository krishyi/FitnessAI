from unittest import result

import requests
from src.config import Config
from src.shared import lookup_known_weight, is_plausible_density


class USDAAPIClient:
    def __init__(self):
        Config.validate()
        self.base_url = Config.USDA_BASE_URL
        self.api_key = Config.USDA_API_KEY

    def raw_search(self, food_name, page_size=20):
        """Hit USDA's search endpoint, return raw unranked results."""
        try:
            response = requests.get(
                f"{self.base_url}foods/search",
                params={"query": food_name, "api_key": self.api_key, "pageSize": page_size},
                timeout=10,
            )
            response.raise_for_status()
            return response.json().get("foods", [])
        except Exception as e:
            print(f"[USDA] search error for '{food_name}': {e}")
            return []

    def calories_for_result(self, result, quantity=1, food_name=None):
        if result is None:
            return {"calories": None, "confidence": None}

        data_type = result.get("dataType", "")
        if data_type == "Branded":
            calories_per_serving = self._get_branded_calories(result)
            confidence = "usda_label" if calories_per_serving is not None else None
        else:
            calories_per_serving, confidence = self._get_generic_calories(result, food_name)

        if calories_per_serving is None:
            return {"calories": None, "confidence": None}

        return {"calories": round(calories_per_serving * quantity, 1), "confidence": confidence}

    def _get_generic_calories(self, result, food_name=None):
        calories_per_100g = self._extract_energy(result.get("foodNutrients", []))

        if calories_per_100g is None:
            fdc_id = result.get("fdcId")
            if fdc_id:
                details = self._fetch_food_details(fdc_id)
                if details:
                    calories_per_100g = self._extract_energy(details.get("foodNutrients", []), nested=True)

        if not is_plausible_density(calories_per_100g):
            if calories_per_100g is not None:
                print(f"[plausibility] rejecting implausible density: {calories_per_100g} kcal/100g for '{food_name}'")
            return None, None

        serving_size_g, confidence = self._resolve_typical_serving_grams(result, food_name)
        return (calories_per_100g / 100) * serving_size_g, confidence

    def _get_branded_calories(self, result):
        label_nutrients = result.get("labelNutrients", {})
        calories = label_nutrients.get("calories", {}).get("value")
        if calories is None:
            return None

    # Cross-check the label value against the record's own per-100g
    # density figure, when available - catches a label value that's
    # inconsistent with the product's own nutrient panel.
        per_100g = self._extract_energy(result.get("foodNutrients", []))
        serving_size = result.get("servingSize")
        serving_unit = (result.get("servingSizeUnit") or "").lower()
        if per_100g is not None and serving_size and serving_unit == "g":
            implied_per_100g = (calories / serving_size) * 100
            if not is_plausible_density(implied_per_100g):
                print(f"[plausibility] rejecting branded label: {calories} cal/{serving_size}g (implies {implied_per_100g:.0f} kcal/100g)")
                return None

        return float(calories)

    def _extract_energy(self, nutrients, nested=False):
        """
        Search-result and detail-endpoint nutrient shapes differ: search
        results are flat ({"nutrientName", "unitName", "value"}), detail
        records nest under "nutrient" ({"nutrient": {"name", "unitName"},
        "amount"}). Handle both explicitly.
        """
        for n in nutrients:
            if nested:
                info = n.get("nutrient", {})
                name = info.get("name", "")
                unit = info.get("unitName", "")
                value = n.get("amount")
            else:
                name = n.get("nutrientName", "")
                unit = n.get("unitName", "")
                value = n.get("value")
            if "Energy" in name and unit == "KCAL":
                return value
        return None

    def _resolve_typical_serving_grams(self, result, food_name=None):
        if food_name:
            grams = lookup_known_weight(food_name)
            if grams:
                print(f"[serving] using known reference weight: {grams}g")
                return grams, "table"

        serving_size = result.get("servingSize")
        serving_unit = (result.get("servingSizeUnit") or "").lower()
        if serving_size and serving_unit == "g":
            return serving_size, "usda_serving_size"

        fdc_id = result.get("fdcId")
        if fdc_id:
            details = self._fetch_food_details(fdc_id)
            if details:
                for portion in details.get("foodPortions", []):
                    gram_weight = portion.get("gramWeight")
                    if gram_weight:
                        return gram_weight, "usda_portion"

        return 100, "fallback_100g"

    def _fetch_food_details(self, fdc_id):
        try:
            response = requests.get(
                f"{self.base_url}food/{fdc_id}",
                params={"api_key": self.api_key},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[USDA] detail fetch error for fdcId {fdc_id}: {e}")
            return None