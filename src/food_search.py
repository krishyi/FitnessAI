import concurrent.futures
from src.shared import relevance_score

def get_combined_candidates(food_name, usda_client, off_client, top_n=8):
    """
    Search USDA and Open Food Facts in parallel, normalize both into a
    common shape, and rank them together - the best match wins regardless
    of source.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        usda_future = executor.submit(usda_client.raw_search, food_name)
        off_future = executor.submit(off_client.raw_search, food_name)
        usda_results = usda_future.result()
        off_results = off_future.result()

    candidates = []

    for r in usda_results:
        candidates.append({
            "source": "usda",
            "description": r.get("description", ""),
            "type_bonus_key": r.get("dataType", ""),
            "raw": r,
        })

    for p in off_results:
        name = p.get("product_name") or ""
        if not name:
            continue
        brand = p.get("brands") or ""
        description = f"{brand} {name}".strip() if brand else name
        candidates.append({
            "source": "off",
            "description": description,
            "type_bonus_key": "Branded",
            "raw": p,
        })

    scored = [(relevance_score(c, food_name), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_n]]


def calories_for_candidate(candidate, usda_client, off_client, quantity=1, food_name=None):
    if candidate is None:
        return {"calories": None, "confidence": None}
    if candidate["source"] == "usda":
        return usda_client.calories_for_result(candidate["raw"], quantity, food_name=food_name)
    return off_client.calories_for_product(candidate["raw"], quantity, food_name=food_name)