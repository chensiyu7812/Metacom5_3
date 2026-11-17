"""Deterministic v0 retrieval. Explicitly not A5 dense/BM25/hybrid retrieval."""
from .v0 import Reader, read, search
__all__=['Reader','read','search']
