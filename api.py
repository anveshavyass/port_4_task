from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.router import route_ticket

app = FastAPI(title="Routely API")


class RouteRequest(BaseModel):
    ticket: str


class BatchRouteRequest(BaseModel):
    tickets: list[str]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/route")
def route(request: RouteRequest) -> dict[str, Any]:
    return route_ticket(request.ticket)


@app.post("/route/batch")
def route_batch(request: BatchRouteRequest) -> list[dict[str, Any]]:
    return [route_ticket(text) for text in request.tickets]
