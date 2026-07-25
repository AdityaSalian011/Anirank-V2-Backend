from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from sqlalchemy.orm import Session
from sqlalchemy import text   ## CRON JOB

from database import engine, Base, get_db
from models import User, Feedback
from schemas import UserCreate, UserLogin, UserOut, Token, FeedbackRequest
from auth import hash_password, verify_password, create_access_token, get_current_user_optional, get_current_user

import os
import math

import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


df = None
embeddings = None
row_ids = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global df, embeddings, row_ids

    df = pd.read_csv("data/best_anime_ds.csv")

    data = np.load("data/context_embeddings.npz")
    embeddings = data["embeddings"]
    row_ids = data["row_ids"]

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://127.0.0.1:5500',
        "http://localhost:5500",
        os.getenv('FRONTEND_URL')
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)


@app.get('/health')
def health_check(db: Session = Depends(get_db)):
    try:
        # Run a lightweight query to keep Supabase awake
        db.execute(text('SELECT 1'))
        return {'status': 'ok', 'db': 'connected'}
    except Exception as e:
        return {'status': 'ok', 'db': 'error', 'detail': str(e)}


@app.post('/auth/signup', response_model=UserOut, status_code=201)
async def signup(req: UserCreate, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email==req.email).first()

    if exists:
        raise HTTPException(status_code=400, detail='Email already registered.')
        
    user = User(email=req.email, hashed_password=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post('/auth/login', response_model=Token)
async def login(req: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email==req.email).first()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=400, detail=f"Invalid email or password.")

    token = create_access_token(data={'sub': str(user.id)})
    return Token(access_token=token)


@app.post('/auth/logout')
async def logout(current_user: User = Depends(get_current_user)):
    return {"detail": "Logged out. Please discard your access token client-side."}


@app.get('/auth/me', response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


def to_records(df: pd.DataFrame):
    """Converts NaN -> None so Starlette's strict JSON encoder doesn't choke on it."""
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                record[key] = None
    return records


@app.get("/top/ranked")
async def top_ranked_animes():
    top_ranked = df.sort_values(by="rank", ascending=True).head(10)
    return to_records(top_ranked)


@app.get("/top/popular")
async def most_popular_animes():
    most_popular = df.sort_values(by="popularity_rank", ascending=False).head(10)
    return to_records(most_popular)


@app.get("/top/engaging")
async def most_engaging_animes():
    most_engaging = df.sort_values(by="engagement_score", ascending=False).head(10)
    return to_records(most_engaging)


@app.get("/recommendations/anime/{mal_id}")
async def recommend_animes(
    mal_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    match_df = df[df["mal_id"]==mal_id]
    
    if match_df.empty:
        return f"Anime with mal_id {mal_id} not found."
    
    query_vector = embeddings[[match_df.index[0]]]
    
    sim = cosine_similarity(query_vector, embeddings)[0]

    if current_user is not None:
        feedback = db.query(Feedback).filter(Feedback.user_id==current_user.id).all()

        interested_anime_ids = [f.mal_id for f in feedback if f.feedback == 1]
        not_interested_anime_ids = [f.mal_id for f in feedback if f.feedback == -1]

        seen_ids = set(interested_anime_ids) | set(not_interested_anime_ids)
        for mid in seen_ids:
            idx = np.where(row_ids == mid)[0].item()
            sim[idx] = -1

    sim = list(enumerate(sim))
    sim = sorted(sim, key=lambda x: x[1], reverse=True)
    sim = sim[1: 11]
    
    anime_indices = [i[0] for i in sim]
    recommend_df = df.iloc[anime_indices]
    return {
        "anchor": to_records(match_df),
        "recommendations": to_records(recommend_df)
    }


@app.get("/genres")
def get_unique_genres():
    """Returns unique genres as a list"""
    unique_genre = set()
    
    for genre in df['genres'].unique():
        unique_genre.update(genre.split(', '))
    
    return sorted(unique_genre)


@app.get("/recommendations/genre/{genre}")
async def popular_genre_animes(genre: str):

    mask = pd.Series([True]* len(df), index=df.index)
    mask &= df["genres"].str.contains(genre, case=False, na=False)

    genre_df = df[mask]
    if genre_df.empty:
        raise HTTPException(status_code=404, detail=f"Anime with {genre} genre not found.")

    popular_genre = genre_df.sort_values(by="popularity_rank", ascending=False).head(10)

    return to_records(popular_genre)


@app.get("/recommendations/smart")
async def recommend_animes_smartly(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    lambda_=0.3
):

    feedback = db.query(Feedback).filter(Feedback.user_id==current_user.id).all()

    if len(feedback) < 2:
        return None

    interested_anime_ids = [f.mal_id for f in feedback if f.feedback == 1]
    not_interested_anime_ids = [f.mal_id for f in feedback if f.feedback == -1]
    
    interested_anime_idx = [np.where(row_ids == mal_id)[0].item() for mal_id in interested_anime_ids]
    not_interested_anime_idx = [np.where(row_ids == mal_id)[0].item() for mal_id in not_interested_anime_ids]

    if not interested_anime_idx:
        return None

    profile = embeddings[interested_anime_idx].mean(axis=0)
    if not_interested_anime_idx:
        profile -= lambda_* embeddings[not_interested_anime_idx].mean(axis=0)

    sim = cosine_similarity([profile], embeddings)[0]

    seen_idx = set(interested_anime_idx) | set(not_interested_anime_idx)
    for mid in seen_idx:
        sim[mid] = -1

    sim = list(enumerate(sim))
    sim = sorted(sim, key=lambda x: x[1], reverse=True)
    sim = sim[0: 10]

    anime_indices = [i[0] for i in sim]
    recommend_df = df.iloc[anime_indices]
    return to_records(recommend_df)


@app.get("/recommendations/recent/{recency}") 
async def recommend_on_recently_seen(
    recency: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    feedback = db.query(Feedback).filter(Feedback.user_id==current_user.id).order_by(Feedback.created_at.desc()).all()

    if not feedback:
        return None

    interested_anime_ids = [f.mal_id for f in feedback if f.feedback == 1]
    not_interested_anime_ids = [f.mal_id for f in feedback if f.feedback == -1]

    if interested_anime_ids and len(interested_anime_ids) >= recency:
        recent_interest = interested_anime_ids[recency-1]
        recent_interest_idx = np.where(row_ids==recent_interest)[0].item()

        query_vector = embeddings[recent_interest_idx]
        sim = cosine_similarity([query_vector], embeddings)[0]

        seen_ids = set(interested_anime_ids) | set(not_interested_anime_ids)
        for mid in seen_ids:
            idx = np.where(row_ids == mid)[0].item()
            sim[idx] = -1

        sim = list(enumerate(sim))
        sim = sorted(sim, key=lambda x: x[1], reverse=True)
        sim = sim[0: 10]
        
        anime_indices = [i[0] for i in sim]
        recommend_df = df.iloc[anime_indices]
        return {
            "anchor": df.iloc[recent_interest_idx]["title"],
            "recommendations": to_records(recommend_df)
        }

    return None


@app.post("/feedback")
async def user_feedback(
    req: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    existing = db.query(Feedback).filter(
        Feedback.user_id==current_user.id,
        Feedback.mal_id==req.mal_id
    ).first()

    if existing:
        existing.feedback = req.feedback
        db.commit()
        db.refresh(existing)
        return "Feedback updated successfully."
    
    feedback = Feedback(user_id=current_user.id, mal_id=req.mal_id, feedback=req.feedback)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return "Feedback saved successfully."

@app.get('/search')
async def seach_engine(query: str):
    mask = df['title'].str.contains(query, case=False, na=False)

    result_df = df[mask].head(5)
    if result_df.empty:
        raise HTTPException(status_code=404, detail=f"Couldn't find {query}...")

    return to_records(result_df)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)