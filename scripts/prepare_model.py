"""Download the public embedding weights during the Vercel build, not per request."""

from pathlib import Path

from fastembed import TextEmbedding

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    model = TextEmbedding(
        model_name="BAAI/bge-small-en-v1.5", cache_dir=str(root / ".model-cache"), threads=2
    )
    vector = next(model.embed(["Build-time embedding model verification."]))
    if len(vector) != 384:
        raise RuntimeError("Unexpected embedding dimensions.")
    print("Embedding model cached and verified: 384 dimensions.")
