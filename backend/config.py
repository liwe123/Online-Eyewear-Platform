import os
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

MODEL_API_URL = os.environ.get("MODEL_API_URL", "http://localhost:8000")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "5000"))