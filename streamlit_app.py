import streamlit as st
import pandas as pd
import joblib
from datetime import date

# ==========================================
# PAGE SETTINGS
# ==========================================

st.set_page_config(
    page_title="DynamicShelf | Smart Pricing",
    page_icon="📦",
    layout="wide"
)

# ==========================================
# LOAD MODEL
# ==========================================

model = joblib.load(
    "ML_Model/dynamic_discount_model.pkl"
)

# ==========================================
# HEADER
# ==========================================

st.title("📦 DynamicShelf")
st.subheader("Smart Pricing for Near-Expiry Products")

st.write(
    "DynamicShelf predicts the recommended discount "
    "and selling price for products approaching expiry."
)

st.divider()

# ==========================================
# PRODUCT DETAILS
# ==========================================

st.header("🛒 Product Details")

col1, col2 = st.columns(2)

with col1:

    category = st.selectbox(
        "Product Category",
        [
            "Dairy",
            "Beverages",
            "Snacks",
            "Personal Care",
            "Other"
        ]
    )

    expiry_date = st.date_input(
        "Expiry Date",
        min_value=date.today()
    )

    base_price = st.number_input(
        "Original Price (₹)",
        min_value=1.0,
        value=100.0
    )

with col2:

    stock_quantity = st.number_input(
        "Stock Quantity",
        min_value=1,
        value=50
    )

    daily_demand = st.number_input(
        "Daily Demand",
        min_value=0.0,
        value=15.0
    )

    spoilage_risk = st.slider(
        "Spoilage Risk",
        0.0,
        1.0,
        0.8
    )

# ==========================================
# PREDICTION
# ==========================================

if st.button("🔮 Predict Discount", type="primary"):

    days_until_expiry = (
        expiry_date - date.today()
    ).days

    # Expiry status

    if days_until_expiry > 30:
        expiry_status = "Safe"

    elif days_until_expiry > 7:
        expiry_status = "Expiring Soon"

    else:
        expiry_status = "Critical"

    # ======================================
    # MODEL INPUT
    # ======================================

    product = pd.DataFrame([{

        "category": category,

        "days_until_expiry": days_until_expiry,

        "shelf_life_days": 10,

        "base_price": base_price,

        "cost_price": base_price * 0.6,

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

    # ======================================
    # PREDICTION
    # ======================================

    predicted_discount = model.predict(product)[0]

    predicted_discount = max(
        0,
        min(predicted_discount, 0.75)
    )

    discount = round(
        predicted_discount * 100,
        2
    )

    recommended_price = round(
        base_price * (1 - predicted_discount),
        2
    )

    # ======================================
    # RESULTS
    # ======================================

    st.divider()

    st.header("📊 Prediction Result")

    r1, r2, r3, r4 = st.columns(4)

    with r1:
        st.metric(
            "Days Until Expiry",
            f"{days_until_expiry} Days"
        )

    with r2:
        st.metric(
            "Expiry Status",
            expiry_status
        )

    with r3:
        st.metric(
            "Recommended Discount",
            f"{discount}%"
        )

    with r4:
        st.metric(
            "Recommended Price",
            f"₹{recommended_price}"
        )

    st.success(
        f"Recommended selling price is ₹{recommended_price} "
        f"after applying {discount}% discount."
    )