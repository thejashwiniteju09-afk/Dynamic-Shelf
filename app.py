from flask import Flask, render_template, request
import pandas as pd
import joblib
import easyocr
import os
import re
import sqlite3
from datetime import date
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Upload folder
UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# OCR Reader
reader = easyocr.Reader(["en"])

# Load ML model
model = joblib.load("ML_Model/dynamic_discount_model.pkl")


# ==========================================
# DATABASE
# ==========================================

def init_db():

    conn = sqlite3.connect("history.db")

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            original_price REAL,
            expiry_date TEXT,
            days_left INTEGER,
            discount REAL,
            recommended_price REAL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    conn = sqlite3.connect("history.db")
    cursor = conn.cursor()

    # Get prediction history
    cursor.execute("""
        SELECT category,
               original_price,
               expiry_date,
               days_left,
               discount,
               recommended_price
        FROM predictions
        ORDER BY id DESC
    """)

    history = cursor.fetchall()


    # ==========================================
    # DASHBOARD SUMMARY
    # ==========================================

    cursor.execute("""
        SELECT COUNT(*),
               AVG(discount),
               AVG(recommended_price)
        FROM predictions
    """)

    summary = cursor.fetchone()

    total_predictions = summary[0] or 0

    average_discount = (
        round(summary[1], 2)
        if summary[1] is not None
        else 0
    )

    average_price = (
        round(summary[2], 2)
        if summary[2] is not None
        else 0
    )


    # Close database only after all queries are complete
    conn.close()


    return render_template(
        "index.html",
        history=history,
        total_predictions=total_predictions,
        average_discount=average_discount,
        average_price=average_price
    )


# ==========================================
# SAVE PREDICTION
# ==========================================

def save_prediction(
    category,
    original_price,
    expiry_date,
    days_left,
    discount,
    recommended_price
):

    conn = sqlite3.connect("history.db")

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO predictions
        (
            category,
            original_price,
            expiry_date,
            days_left,
            discount,
            recommended_price
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        category,
        original_price,
        expiry_date,
        days_left,
        discount,
        recommended_price
    ))

    conn.commit()
    conn.close()
# ==========================================
# GET PREDICTION HISTORY
# ==========================================

def get_history():

    conn = sqlite3.connect("history.db")

    cursor = conn.cursor()

    cursor.execute("""
        SELECT category,
               original_price,
               expiry_date,
               days_left,
               discount,
               recommended_price
        FROM predictions
        ORDER BY id DESC
    """)

    history = cursor.fetchall()

    conn.close()

    return history


# ==========================================
# SCAN + AUTOMATIC PREDICTION
# ==========================================

@app.route("/scan", methods=["POST"])
def scan():

    if "image" not in request.files:
        return "No image uploaded"

    image = request.files["image"]

    if image.filename == "":
        return "No image selected"

    # Save image
    filename = secure_filename(image.filename)

    filepath = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    image.save(filepath)

    # OCR
    result = reader.readtext(
        filepath,
        detail=0
    )

    extracted_text = " ".join(result)


    # ==========================================
    # EXTRACT PRODUCT CATEGORY
    # ==========================================

    extracted_category = ""

    text_lower = extracted_text.lower()

    if any(word in text_lower for word in [
        "shampoo",
        "soap",
        "cream",
        "lotion",
        "moisturizer",
        "face wash"
    ]):

        extracted_category = "Personal Care"

    elif any(word in text_lower for word in [
        "milk",
        "cheese",
        "butter",
        "curd",
        "yogurt"
    ]):

        extracted_category = "Dairy"

    elif any(word in text_lower for word in [
        "juice",
        "drink",
        "water",
        "beverage"
    ]):

        extracted_category = "Beverages"

    elif any(word in text_lower for word in [
        "chips",
        "biscuit",
        "snack"
    ]):

        extracted_category = "Snacks"

    else:

        extracted_category = "Other"
# ==========================================
# EXTRACT MRP / PRICE
# ==========================================

    extracted_price = ""

# Normalize OCR text
    price_text = extracted_text

# Different possible ways OCR may read MRP
    price_patterns = [

    # MRP ... ₹ 349.00
        r"MRP.*?₹\s*(\d+(?:\.\d{1,2})?)",

    # MRP ... Rs. 349.00
        r"MRP.*?Rs\.?\s*(\d+(?:\.\d{1,2})?)",

    # MRP ... 349.00
        r"MRP.*?(\d+\.\d{1,2})",

    # ₹ 349.00
        r"₹\s*(\d+(?:\.\d{1,2})?)",

    # Rs. 349.00
        r"Rs\.?\s*(\d+(?:\.\d{1,2})?)"

    ]

    for pattern in price_patterns:

        price_match = re.search(
            pattern,
            price_text,
            re.IGNORECASE
        )

        if price_match:

            extracted_price = float(
                price_match.group(1)
            )

            break
# ==========================================
# EXTRACT EXPIRY DATE
# ==========================================

    extracted_expiry = ""

    expiry_patterns = [

    # Use Before: 04/2028
        r"(?:USE\s*BEFORE|USE\s*BY|BEST\s*BEFORE)"
        r".{0,30}?"
        r"(0[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})",

    # EXPIRY: 04/2028
        r"(?:EXPIRY|EXP\.?\s*DATE)"
        r".{0,30}?"
        r"(0[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})"

    ]

    for pattern in expiry_patterns:

        expiry_match = re.search(
            pattern,
            extracted_text,
            re.IGNORECASE
        )

        if expiry_match:

            month = int(expiry_match.group(1))
            year = int(expiry_match.group(2))

            extracted_expiry = (
                f"{year}-{month:02d}-28"
            )

            break


    # ==========================================
    # DEFAULT VALUES
    # ==========================================

    category = extracted_category

    stock_quantity = 50

    daily_demand = 15

    spoilage_risk = 0.8


    # Prediction values

    prediction = False

    discount = None

    recommended_price = None

    days_left = None

    expiry_status="Not available"


    # ==========================================
    # AUTOMATIC PREDICTION
    # ==========================================

    if extracted_price and extracted_expiry:

        expiry_date = date.fromisoformat(
            extracted_expiry
        )

        days_left = (
            expiry_date - date.today()
        ).days
        # ==========================================
        # EXPIRY STATUS
        # ==========================================

        if days_until_expiry > 30:
            expiry_status = "Safe"

        elif days_until_expiry > 7:
            expiry_status = "Expiring Soon"

        else:
            expiry_status = "Critical"

        product = pd.DataFrame([{

            "category": category,

            "days_until_expiry": days_left,

            "shelf_life_days": 10,

            "base_price": extracted_price,

            "cost_price": extracted_price * 0.6,

            "initial_quantity": stock_quantity,

            "daily_demand": daily_demand,

            "demand_variability": 2,

            "spoilage_sensitivity": 0.8,

            "spoilage_risk": spoilage_risk,

            "storage_temp": 4,

            "temp_deviation": 1,

            "is_weekend": 0,

            "month": date.today().month,

            "is_promoted": 0

        }])


        predicted_discount = model.predict(
            product
        )[0]


        predicted_discount = max(
            0,
            min(predicted_discount, 0.75)
        )


        discount = round(
            predicted_discount * 100,
            2
        )


        recommended_price = round(

            extracted_price *
            (1 - predicted_discount),

            2
        )


        prediction = True


        # SAVE TO DATABASE

        save_prediction(

            category,

            extracted_price,

            extracted_expiry,

            days_left,

            discount,

            recommended_price

        )


    return render_template(

        "index.html",

        extracted_text=extracted_text,

        extracted_category=extracted_category,

        extracted_price=extracted_price,

        extracted_expiry=extracted_expiry,

        prediction=prediction,

        discount=discount,

        price=recommended_price,

        days_left=days_left,

        expiry_status=expiry_status,

        history=get_history()

    )


# ==========================================
# MANUAL PREDICTION
# ==========================================

@app.route("/predict", methods=["POST"])
def predict():

    category = request.form["category"]

    expiry_date = request.form["expiry_date"]

    base_price = float(
        request.form["base_price"]
    )

    expiry = date.fromisoformat(
        expiry_date
    )

    days_until_expiry = (
        expiry - date.today()
    ).days
    # ==========================================
    # EXPIRY STATUS
    # ==========================================

    if days_until_expiry > 30:
        expiry_status = "Safe"

    elif days_until_expiry > 7:
        expiry_status = "Expiring Soon"

    else:
        expiry_status = "Critical"

    stock_quantity = int(
        request.form["stock_quantity"]
    )

    daily_demand = float(
        request.form["daily_demand"]
    )

    spoilage_risk = float(
        request.form["spoilage_risk"]
    )


    product = pd.DataFrame([{

        "category": category,

        "days_until_expiry":
            days_until_expiry,

        "shelf_life_days": 10,

        "base_price": base_price,

        "cost_price":
            base_price * 0.6,

        "initial_quantity":
            stock_quantity,

        "daily_demand":
            daily_demand,

        "demand_variability": 2,

        "spoilage_sensitivity": 0.8,

        "spoilage_risk":
            spoilage_risk,

        "storage_temp": 4,

        "temp_deviation": 1,

        "is_weekend": 0,

        "month": date.today().month,

        "is_promoted": 0

    }])


    predicted_discount = model.predict(
        product
    )[0]


    predicted_discount = max(
        0,
        min(predicted_discount, 0.75)
    )


    discount = round(
        predicted_discount * 100,
        2
    )


    recommended_price = round(

        base_price *
        (1 - predicted_discount),

        2
    )


    # SAVE TO DATABASE

    save_prediction(

        category,

        base_price,

        expiry_date,

        days_until_expiry,

        discount,

        recommended_price

    )


    return render_template(

        "index.html",

        extracted_category=category,

        extracted_price=base_price,

        extracted_expiry=expiry_date,

        prediction=True,

        discount=discount,

        price=recommended_price,

        days_left=days_until_expiry,

        expiry_status=expiry_status,

        history=get_history()

    )
# ==========================================
# CLEAR PREDICTION HISTORY
# ==========================================

@app.route("/clear-history")
def clear_history():

    conn = sqlite3.connect("history.db")

    cursor = conn.cursor()

    cursor.execute("DELETE FROM predictions")

    conn.commit()

    conn.close()

    return home()

# ==========================================
# RUN APP
# ==========================================

if __name__ == "__main__":

    app.run(debug=True)