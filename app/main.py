""" Main application and routing logic for API """

import uvicorn

from app.vocab_search import VocabSearch

# pylint: disable=invalid-name
app = VocabSearch

if __name__ == "__main__":  # pragma: no cover
    uvicorn.run("app.vocab_search:VocabSearch", host="0.0.0.0", port=8002, workers=1)
