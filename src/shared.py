import re

FILLER_WORDS = {"a", "an", "the", "of", "some"}

COMPONENT_QUALIFIERS = {
    "white", "yolk", "substitute", "powder", "dried", "freeze-dried",
    "custard", "beaten", "mix", "flavored", "imitation",
    "flour", "starch", "syrup", "extract", "concentrate", "isolate",
    "back", "neck", "feet", "foot", "wingtip", "skin", "fat", "bone",
    "giblet", "giblets", "liver", "gizzard", "heart", "kidney", "brain",
    "tongue", "tripe", "trotter", "snout", "rind", "tail", "organ",
    "offal", "sweetbread", "marrow", "jowl", "ear", "roe",
    # Cooking-state words that meaningfully change calories and
    # shouldn't be assumed unless the user actually said them - "raw"
    # underestimates real intake, "fried"/"battered"/"breaded" overstate
    # it if the food was actually plain-cooked. Bare "chicken breast"
    # should default to a plain cooked entry, not raw or fried.
    "raw", "fried", "battered", "breaded",
}

TYPE_BONUS = {
    "Foundation": 0.5,
    "SR Legacy": 0.5,
    "Survey (FNDDS)": 0.2,
    "Branded": 0,
}

# Cooking/prep words that don't change WHICH item is being referred to -
# "boneless skinless chicken breast" should still match the "chicken
# breast" weight entry below, not be treated as unmatched just because
# of these descriptive extras.
ALLOWED_SERVING_MODIFIERS = {
    "grilled", "boneless", "skinless", "cooked", "raw", "fried",
    "baked", "roasted", "broiled", "lean", "trimmed", "fresh", "whole",
}

# Typical reference weights (grams) for common single-unit foods and meat/protein cuts
COMMON_ITEM_GRAMS = {
    frozenset({"egg"}): 50,
    frozenset({"banana"}): 118,
    frozenset({"apple"}): 182,
    frozenset({"orange"}): 131,
    frozenset({"slice"}): 28,
    frozenset({"clove"}): 3,
    frozenset({"cup"}): 240,
    frozenset({"chicken", "breast"}): 174,
    frozenset({"chicken", "thigh"}): 110,
    frozenset({"chicken", "drumstick"}): 100,
    frozenset({"chicken", "wing"}): 90,
    frozenset({"pork", "chop"}): 150,
    frozenset({"steak"}): 227,
    frozenset({"salmon", "fillet"}): 170,
    frozenset({"fish", "fillet"}): 170,
    frozenset({"burger", "patty"}): 113,
    frozenset({"bun"}): 50,
    frozenset({"bagel"}): 105,
    frozenset({"tortilla"}): 45,
}


def canonical_words(text):
    words = re.findall(r"[a-z]+", text.lower())
    canonical_list = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]
    return canonical_list, set(canonical_list)


def relevance_score(candidate, query):
    query_list, query_canonical = canonical_words(query)
    desc = candidate.get("description", "")
    desc_list, desc_canonical = canonical_words(desc)

    overlap = len(query_canonical & desc_canonical)
    primary_match = 3 if desc_list and desc_list[0] in query_canonical else 0

    qualifier_penalty = sum(
        1.5 for word in (desc_canonical & COMPONENT_QUALIFIERS) if word not in query_canonical
    )

    length_penalty = len(desc_list) * 0.05
    type_bonus = TYPE_BONUS.get(candidate.get("type_bonus_key"), 0)

    return overlap + primary_match - qualifier_penalty - length_penalty + type_bonus


def is_plausible_density(calories_per_100g):
    """Sanity check on calorie DENSITY (per 100g) - a near-universal
    invariant across foods, unlike a per-serving total."""
    if calories_per_100g is None:
        return False
    return 5 <= calories_per_100g <= 900


def lookup_known_weight(food_name, table=None):
    """
    Match food_name against a table keyed by frozenset-of-canonical-words.
    The key's words must be a SUBSET of the query's meaningful words, and
    any leftover query words must be harmless prep/cooking modifiers -
    not an unrelated word. Ties broken toward the MOST SPECIFIC (largest)
    matching key.
    """
    if table is None:
        table = COMMON_ITEM_GRAMS

    _, canonical = canonical_words(food_name)
    meaningful = canonical - FILLER_WORDS

    matches = []
    for key_set, grams in table.items():
        if key_set <= meaningful:
            leftover = meaningful - key_set
            if leftover <= ALLOWED_SERVING_MODIFIERS:
                matches.append((len(key_set), grams))

    if not matches:
        return None

    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]