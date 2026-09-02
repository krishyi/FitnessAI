const API_URL = "http://localhost:8000";

const LB_PER_KG = 2.20462;
const IN_PER_CM = 0.393701;

function convertWeight(value, from, to) {
    if (from === to) return value;
    return from === "kg" ? value * LB_PER_KG : value / LB_PER_KG;
}

function convertHeight(value, from, to) {
    if (from === to) return value;
    return from === "cm" ? value * IN_PER_CM : value / IN_PER_CM;
}

function setupUnitToggle(toggleEl, inputEl, convert) {
    const buttons = toggleEl.querySelectorAll(".unit-btn");
    buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.classList.contains("active")) return;
            const fromUnit = toggleEl.querySelector(".active").dataset.unit;
            const toUnit = btn.dataset.unit;

            const currentValue = parseFloat(inputEl.value);
            if (!isNaN(currentValue)) {
                inputEl.value = Math.round(convert(currentValue, fromUnit, toUnit) * 10) / 10;
            }

            buttons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
        });
    });
}

function getWeightKg() {
    const value = parseFloat(document.getElementById("weightInput").value);
    if (isNaN(value)) return null;
    const unit = document.querySelector('.unit-toggle[data-target="weight"] .active').dataset.unit;
    return unit === "kg" ? value : value / LB_PER_KG;
}

function getHeightCm() {
    const value = parseFloat(document.getElementById("heightInput").value);
    if (isNaN(value)) return null;
    const unit = document.querySelector('.unit-toggle[data-target="height"] .active').dataset.unit;
    return unit === "cm" ? value : value / IN_PER_CM;
}

document.addEventListener("DOMContentLoaded", () => {
    setupUnitToggle(document.querySelector('.unit-toggle[data-target="weight"]'), document.getElementById("weightInput"), convertWeight);
    setupUnitToggle(document.querySelector('.unit-toggle[data-target="height"]'), document.getElementById("heightInput"), convertHeight);

    document.getElementById("toggleBreakdownBtn").addEventListener("click", () => {
        const foodList = document.getElementById("foodList");
        const btn = document.getElementById("toggleBreakdownBtn");
        foodList.hidden = !foodList.hidden;
        btn.textContent = foodList.hidden ? "Show details" : "Hide details";
    });
});

document.getElementById("analyzeBtn").addEventListener("click", analyzeMeal);

async function analyzeMeal() {
    const text = document.getElementById("mealInput").value.trim();
    if (!text) {
        alert("Please describe what you ate.");
        return;
    }

    const button = document.getElementById("analyzeBtn");
    setLoading(button, true);

    try {
        const response = await fetch(`${API_URL}/analyze-meal`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        const data = await response.json();
        renderResults(data);
        refreshDailyTotal();
    } catch (error) {
        console.error("Error analyzing meal:", error);
        alert("Something went wrong — is the backend running?");
    } finally {
        setLoading(button, false);
    }
}

document.getElementById("fitnessAdviceBtn").addEventListener("click", getFitnessAdvice);

async function getFitnessAdvice() {
    const weight_kg = getWeightKg();
    const height_cm = getHeightCm();
    const goal = document.getElementById("goalInput").value;
    const activity_level = document.getElementById("activityInput").value;

    if (!weight_kg || !height_cm) {
        alert("Please enter your weight and height.");
        return;
    }

    const button = document.getElementById("fitnessAdviceBtn");
    setLoading(button, true);

    try {
        const response = await fetch(`${API_URL}/fitness-advice`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ weight_kg, height_cm, goal, activity_level }),
        });
        const data = await response.json();

        document.getElementById("bmiValue").textContent = data.bmi;
        document.getElementById("bmiCategory").textContent = data.bmi_category;
        document.getElementById("fitnessAdviceText").textContent =
            data.advice || "Couldn't generate advice right now — try again.";
        document.getElementById("fitnessResults").style.display = "block";
    } catch (error) {
        console.error("Error getting fitness advice:", error);
        alert("Something went wrong — is the backend running?");
    } finally {
        setLoading(button, false);
    }
}

document.getElementById("askFitnessBtn").addEventListener("click", askFitnessQuestion);

async function askFitnessQuestion() {
    const question = document.getElementById("fitnessQuestionInput").value.trim();
    if (!question) {
        alert("Please type a question.");
        return;
    }

    const payload = { question };
    if (document.getElementById("useProfileToggle").checked) {
        const weight_kg = getWeightKg();
        const height_cm = getHeightCm();
        if (weight_kg && height_cm) {
            payload.weight_kg = weight_kg;
            payload.height_cm = height_cm;
            payload.goal = document.getElementById("goalInput").value;
            payload.activity_level = document.getElementById("activityInput").value;
        }
    }

    const button = document.getElementById("askFitnessBtn");
    setLoading(button, true);

    try {
        const response = await fetch(`${API_URL}/fitness-chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        appendQAEntry(data.question, data.answer);
        document.getElementById("fitnessQuestionInput").value = "";
    } catch (error) {
        console.error("Error asking fitness question:", error);
        alert("Something went wrong — is the backend running?");
    } finally {
        setLoading(button, false);
    }
}

function appendQAEntry(question, answer) {
    const history = document.getElementById("fitnessQAHistory");
    const entry = document.createElement("div");
    entry.className = "qa-entry";
    entry.innerHTML = `<p><strong>You:</strong> ${question}</p><p><strong>Coach:</strong> ${answer}</p>`;
    history.prepend(entry); // newest on top
}

function setLoading(button, isLoading) {
    button.disabled = isLoading;
    button.classList.toggle("loading", isLoading);
}

function renderResults(data) {
    const resultsSection = document.getElementById("resultsSection");
    const foodList = document.getElementById("foodList");

    foodList.innerHTML = "";
    data.foods.forEach((food) => {
        const item = document.createElement("p");
        if (food.calories !== null) {
            const confidenceNote =
                food.confidence === "ai_estimate" ? " ⚠️ AI estimate — not verified" :
                food.confidence === "fallback_100g" ? " (rough estimate)" :
                food.confidence === "table" ? " (typical size)" :
                "";
            item.textContent = `${food.quantity}x ${food.name} — ${food.calories} cal${confidenceNote}`;
        } else {
            item.textContent = `${food.quantity}x ${food.name} — couldn't find calorie data`;
        }
        foodList.appendChild(item);
    });

    document.getElementById("totalCalories").textContent = data.total_calories;
    document.getElementById("advice").textContent = data.advice;

    foodList.hidden = true;
    document.getElementById("toggleBreakdownBtn").textContent = "Show details";

    resultsSection.style.display = "block";
}

async function refreshDailyTotal() {
    try {
        const response = await fetch(`${API_URL}/today`);
        const data = await response.json();
        document.getElementById("dailyTotal").textContent = `${data.total_calories} cal`;
    } catch (error) {
        console.error("Error fetching daily total:", error);
    }
}

// Load today's total when the page opens
refreshDailyTotal();