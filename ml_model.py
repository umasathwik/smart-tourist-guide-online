"""Small educational ML pipeline for Smart Tourist Guide."""
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, MinMaxScaler
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "tourist_places.csv"

NUMERIC_FEATURES = ["Cost", "Distance_km", "Visit_Time_hr", "Popularity"]
CATEGORICAL_FEATURES = ["City", "Type"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET_COLUMN = "Rating"


def load_dataset():
    df = pd.read_csv(DATA_PATH)
    df.columns = df.columns.str.strip()
    # Data quality checks/cleaning.
    df = df.drop_duplicates().copy()
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
    df = df.dropna(subset=["Rating"]).copy()
    for col in ["City", "Type", "Place"]:
        df[col] = df[col].astype(str).str.strip()
    return df


def create_preprocessor():
    numeric_pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", MinMaxScaler()),
    ])
    categorical_pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer(transformers=[
        ("numeric", numeric_pipe, NUMERIC_FEATURES),
        ("categorical", categorical_pipe, CATEGORICAL_FEATURES),
    ])


def train_models():
    df = load_dataset()
    X = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].copy()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    linear_model = Pipeline(steps=[
        ("preprocessing", create_preprocessor()),
        ("regression", LinearRegression()),
    ])
    rf_model = Pipeline(steps=[
        ("preprocessing", create_preprocessor()),
        ("regression", RandomForestRegressor(
            n_estimators=120, random_state=42, min_samples_leaf=2
        )),
    ])
    linear_model.fit(X_train, y_train)
    rf_model.fit(X_train, y_train)

    metrics = {}
    for name, model in [("Linear Regression", linear_model), ("Random Forest Regression", rf_model)]:
        pred = model.predict(X_test)
        mse = mean_squared_error(y_test, pred)
        metrics[name] = {
            "MAE": float(mean_absolute_error(y_test, pred)),
            "MSE": float(mse),
            "RMSE": float(np.sqrt(mse)),
            "R2": float(r2_score(y_test, pred)),
        }
    return df, linear_model, rf_model, metrics


df, linear_model, rf_model, MODEL_METRICS = train_models()


def recommend_for_city(city, budget=10000, interest="All", limit=6):
    """Predict ratings for curated sample attractions in the selected city."""
    subset = df[df["City"].str.casefold() == city.strip().casefold()].copy()
    subset = subset[subset["Cost"] <= float(budget)]
    if interest and interest.casefold() != "all":
        subset = subset[subset["Type"].str.casefold() == interest.casefold()]
    if subset.empty:
        return []
    subset["Predicted_Rating"] = np.clip(rf_model.predict(subset[FEATURE_COLUMNS]), 1, 5)
    subset = subset.sort_values(["Predicted_Rating", "Popularity"], ascending=[False, False]).head(limit)
    records = []
    for _, row in subset.iterrows():
        records.append({
            "place": str(row["Place"]),
            "city": str(row["City"]),
            "type": str(row["Type"]),
            "cost": float(row["Cost"]),
            "distance_km": float(row["Distance_km"]),
            "visit_time_hr": float(row["Visit_Time_hr"]),
            "sample_rating": float(row["Rating"]),
            "predicted_rating": float(row["Predicted_Rating"]),
            "lat": float(row["Latitude"]),
            "lon": float(row["Longitude"]),
            "image_search_url": "https://www.google.com/search?tbm=isch&q=" + __import__("urllib.parse", fromlist=["quote"]).quote(f"{row['Place']} {row['City']}"),
        })
    return records
