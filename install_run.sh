# Step 1 — go into the backend folder
cd api-test-generator/backend

# Step 2 — create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # your prompt will show (venv)

# Step 3 — install dependencies
pip install -r requirements.txt

# Step 4 — run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000