"""Open Notebook integration (self-hosted NotebookLM alternative).

Used by the document library "Listen" feature to turn CEO-level briefs
into single-narrator audio reports via Open Notebook's podcast engine.
"""

from services.open_notebook.client import (  # noqa: F401
    OpenNotebookClient,
    OpenNotebookError,
    open_notebook_configured,
)
