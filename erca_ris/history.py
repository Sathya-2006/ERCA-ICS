import csv
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "incidents.csv"


def load_incidents():
    with DATA_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def search_history(query, top_k=5):
    rows = load_incidents()
    if not rows:
        return []

    documents = [
        " ".join([
            r.get("service", ""),
            r.get("error", ""),
            r.get("category", ""),
            r.get("root_cause", ""),
            r.get("resolution", ""),
            r.get("preventive_action", ""),
        ])
        for r in rows
    ]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(documents + [query])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()

    ranked = sorted(zip(scores, rows), key=lambda x: x[0], reverse=True)[:top_k]
    result = []
    for score, row in ranked:
        item = dict(row)
        item["similarity"] = round(float(score), 4)
        result.append(item)
    return result
