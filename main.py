from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from realtime import handle as handle_realtime

load_dotenv(override=True)

app = FastAPI()


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def get():
    with open("static/index.html", "r") as f:
        return f.read()


@app.post("/message/{client_id}")
async def post_message(request: Request, client_id: str):
    data = await request.json()
    return data


@app.websocket("/realtime/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    await handle_realtime(websocket)
