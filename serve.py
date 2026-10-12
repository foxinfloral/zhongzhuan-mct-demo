"""HF Space entrypoint: existing FastAPI API + two static demo pages on one origin."""
import os
from pathlib import Path

import mct_service.feedback as _fb

# Container filesystem is read-only for the app user except /tmp.
_fb.FEEDBACK_DIR = Path(os.environ.get("MCT_FEEDBACK_DIR", "/tmp/mct-feedback"))

from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from mct_service.app import app  # noqa: E402

_STATIC = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def _root():
    return RedirectResponse(url="/min-loop.html", status_code=307)


@app.get("/min-loop.html", include_in_schema=False)
def _min_loop():
    return FileResponse(_STATIC / "min-loop.html", media_type="text/html; charset=utf-8")


@app.get("/index.html", include_in_schema=False)
def _index():
    return FileResponse(_STATIC / "index.html", media_type="text/html; charset=utf-8")
