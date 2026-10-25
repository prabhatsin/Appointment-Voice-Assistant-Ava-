"""Token server plus the metrics endpoints. Run from the project root: uvicorn transport.server:app --reload"""
from transport.token_server import app
from transport.metrics_api import router as metrics_router

app.include_router(metrics_router)
