"""Offline TF-IDF cosine baseline; this is sparse lexical IR, not a neural embedding."""
import math
from collections import Counter
from app.retrieval.bm25 import tokenize


def vectorize(texts: list[str]) -> tuple[list[dict[str,float]], dict[str,int]]:
    tokenized=[tokenize(text) for text in texts]
    df=Counter(token for row in tokenized for token in set(row))
    vocab={term:index for index,term in enumerate(sorted(df))}
    vectors=[]
    for row in tokenized:
        counts=Counter(row)
        vector={}
        for token,count in counts.items():
            tf=1+math.log(count)
            idf=math.log(1+(len(tokenized)+1)/(df[token]+1))
            vector[token]=tf*idf
        norm=math.sqrt(sum(value*value for value in vector.values())) or 1
        vectors.append({token:value/norm for token,value in vector.items()})
    return vectors,vocab


def cosine(left: dict[str,float], right: dict[str,float]) -> float:
    if len(left)>len(right):
        left,right=right,left
    return sum(value*right.get(term,0.0) for term,value in left.items())


def rank(query: str, documents: list[dict], k: int = 10) -> list[dict]:
    texts=[doc.get("text","") for doc in documents]
    from app.providers.factory import get_embedding_provider
    from app.providers.cache import cached_embed
    provider=get_embedding_provider()
    if provider.name=="tfidf":
        vectors=provider.embed([*texts,query],kind="passage")
        q=vectors[-1]
        ranked=[(cosine({str(i):v for i,v in enumerate(q)},{str(i):v for i,v in enumerate(vector)}),doc) for doc,vector in zip(documents,vectors[:-1])]
    else:
        passages=cached_embed(provider,texts,kind="passage")
        q=cached_embed(provider,[query],kind="query")[0]
        ranked=[(sum(a*b for a,b in zip(q,vector)),doc) for doc,vector in zip(documents,passages)]
    return [dict(doc,score=score) for score,doc in sorted(ranked,key=lambda row:(-row[0],row[1].get("repo_id","")))[:k]]
