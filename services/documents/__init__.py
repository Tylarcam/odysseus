"""Document-scoped background services (audio briefs, etc.).

Separate from services/docs (the personal-document RAG facade) so importing
this package never drags in ChromaDB/vector dependencies.
"""
