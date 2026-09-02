def compute_totals(food_list):
    total_calories = sum(item.get("calories", 0) * item.get("quantity", 1) for item in food_list)
    return total_calories

