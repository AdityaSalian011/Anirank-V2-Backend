
FROM python:3.11-slim
 
WORKDIR /app
 
# System deps needed to build psycopg2 / bcrypt wheels if no prebuilt wheel matches
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# Copies app code AND the data/ folder (best_anime_ds.csv, context_embeddings.npz)
# — make sure both are present in the build context, not just in .gitignore-excluded paths
COPY . .
 
# EXPOSE is informational only — Render assigns the real port via $PORT
EXPOSE 10000
 
# Shell form (not exec-form array) so $PORT actually gets expanded.
# Falls back to 10000 (Render's default) if PORT isn't set, e.g. for local `docker run`.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}