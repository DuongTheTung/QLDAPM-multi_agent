import uvicorn

from .config import get_settings

settings = get_settings()
uvicorn.run("backend.app.main:app", host=settings.app_host, port=settings.app_port, reload=False)

