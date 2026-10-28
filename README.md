# Smart Tourist Guide — Online Website + Machine Learning

A beginner-friendly student project that uses **GitHub for source code** and a Python Flask service for the live website. It combines a small educational regression model with route lookup and nearby places from online map sources.

## What it does

- Search a **From** and **To** location (city, landmark, or full address).
- Optionally use the browser's current location after the user grants permission.
- Show a road route, approximate distance and duration when the routing service is available.
- Compare **rough one-way budget estimates** for bus, car, train and airplane.
- Search nearby hotels/guesthouses, restaurants/cafes, and attractions from OpenStreetMap data.
- Show Google Maps search/review links for local places.
- Show sample Machine Learning recommendations for Hyderabad, Vizag, Chennai, Bengaluru, Delhi and Mumbai.
- Demonstrate preprocessing, One-Hot Encoding, Min-Max Scaling, train/test split, Linear Regression, Random Forest Regression and MAE/MSE/RMSE/R² metrics.

## Important limitations

- `data/tourist_places.csv` contains **sample educational values**. Ratings, popularity and attraction costs are not verified live data.
- The ML scores are demonstrations, not real visitor ratings. Replace the sample data with a larger, consistently collected dataset before presenting predictive accuracy as meaningful.
- Bus/train/airplane costs are formula-based estimates, **not live fares**. Car cost is a per-vehicle estimate; other estimates are per passenger.
- OSRM's public demo endpoint is best-effort and does not supply live traffic. If unavailable, the site displays a clearly marked approximate line instead of pretending it is a real road route.
- Nearby venues are fetched from OpenStreetMap and sorted by distance. The free OSM integration does not provide restaurant review ratings, so it cannot honestly call a venue “best-rated.” Users can open Google Maps links to review current venue details.
- Public geocoding/routing/POI endpoints have usage limits and may occasionally be unavailable. This starter is for a small student project, not high-volume production traffic. For a larger public launch, use a supported commercial/geocoding/routing provider or host your own services.
- The maps use OpenStreetMap tiles and require attribution to OpenStreetMap contributors.

## Project files

```text
smart-tourist-guide-full/
├── app.py                     # Flask routes and online APIs
├── ml_model.py                # Preprocessing and regression pipeline
├── requirements.txt           # Python packages
├── Procfile                   # Production start command
├── render.yaml                # Optional Render configuration
├── data/
│   └── tourist_places.csv     # Educational sample dataset
├── templates/
│   └── index.html             # Search website
└── static/
    ├── app.js                 # Search, cards and map behavior
    └── style.css              # Responsive website styling
```

## Run locally in VS Code

1. Download and extract the ZIP.
2. Open the extracted `smart-tourist-guide-full` folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Create a virtual environment (recommended):

   **Windows PowerShell**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   python app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

If Windows Application Control blocks scikit-learn's compiled DLL in your existing Python installation, this is a device/security policy issue rather than an application-code error. Don't try to bypass your device's security controls. You can deploy the backend in Render's managed environment, or ask your administrator to help with the local Python environment.

## Publish using GitHub + Render

**GitHub stores your project code. Render runs the Python backend.** GitHub Pages by itself cannot run Flask/Python server code, so use a Render **Web Service** for this project.

1. Sign in to GitHub and create a repository named `smart-tourist-guide-online`.
2. Upload the files and folders from this project. Keep `app.py`, `ml_model.py`, and `requirements.txt` in the repository root. Keep `templates/`, `static/`, and `data/` as folders.
3. Open Render and sign in: <https://render.com/>.
4. Choose **New → Web Service**, connect GitHub, and select the repository.
5. Use these settings:
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app`
   - **Health check path:** `/health`
6. Deploy. When the build succeeds, open the public `onrender.com` URL supplied by Render.
7. Test the website using a route such as `Hyderabad` → `Visakhapatnam`, then inspect transport estimates and nearby places.

Render can automatically redeploy when you push new commits to the connected GitHub branch. Free services may sleep after inactivity, so the first visit after a quiet period can take longer.

## How the ML is used

- **Inputs:** estimated attraction cost, distance from city centre, expected visit time, popularity score, city and category.
- **Target:** sample attraction rating.
- **Preprocessing:** median imputation + Min-Max scaling for numeric features; most-frequent imputation + One-Hot Encoding for categorical features.
- **Models:** Linear Regression and Random Forest Regression.
- **Evaluation:** MAE, MSE, RMSE and R² on a held-out test split.
- **Website recommendations:** for the six cities represented in the sample dataset, Random Forest predictions rank attractions under the chosen attraction budget and category. For other destinations, live nearby OpenStreetMap places are still shown, but sample ML ranking is not claimed.

## Online sources and attribution

- Map tiles and nearby POIs: OpenStreetMap contributors — <https://www.openstreetmap.org/copyright>
- Location lookup: Nominatim — <https://nominatim.org/> (follow public usage policy; do not use it for autocomplete or high-volume search)
- Road-route estimate: OSRM demo service — <https://project-osrm.org/docs/>
- Attraction thumbnail lookup: Wikipedia page images where available. If no thumbnail is found, the site offers an image-search link.

Check public-service terms and usage policies before increasing traffic. Do not claim live ticket prices or restaurant reviews unless you connect a provider that actually supplies that information.
