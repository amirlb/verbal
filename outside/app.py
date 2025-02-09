import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import httpx
import asyncio
import uvicorn
from os import environ

app = FastAPI()
templates = Jinja2Templates(directory="templates")
http_client = httpx.AsyncClient()

EXCLUDED_HEADERS = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}

async def proxy_request(target: str, request: Request):
    url = f"http://{target}:8000{request.url.path}"
    response = await http_client.request(
        method=request.method,
        url=url,
        headers=request.headers.raw,
        content=await request.body()
    )
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers={name: value for (name, value) in response.headers.items() if name.lower() not in EXCLUDED_HEADERS},
    )
async def proxy_websocket(client: WebSocket, target: str, url_path: str):
    await client.accept()
    async with websockets.connect(f"ws://{target}:8000{url_path}") as ws:
        async def forward_to_client():
            try:
                while True:
                    message = await ws.recv()
                    if isinstance(message, str):
                        await client.send_text(message)
                    else:
                        await client.send_bytes(message)
            except websockets.ConnectionClosed:
                pass

        async def forward_to_server():
            try:
                while True:
                    message = await client.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message['type'] == 'websocket.receive':
                        if 'text' in message:
                            await ws.send(message['text'])
                        elif 'bytes' in message:
                            await ws.send(message['bytes'])
            except websockets.ConnectionClosed:
                pass

        done, pending = await asyncio.wait(
            [
                asyncio.create_task(forward_to_client()),
                asyncio.create_task(forward_to_server())
            ],
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Verbal", "path": "/verbal/", "email": request.headers.get("X-Email")}
    )

@app.get("/staging", response_class=HTMLResponse)
async def staging(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Verbal | Staging", "path": "/verbal-staging/", "email": request.headers.get("X-Email")}
    )

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.route("/verbal{path:path}")
async def verbal(request: Request):
    return await proxy_request("inside", request)

@app.websocket("/verbal/_stcore/stream")
async def verbal_ws(websocket: WebSocket):
    await proxy_websocket(websocket, "inside", "/verbal/_stcore/stream")

@app.route("/verbal-staging{path:path}")
async def verbal_staging(request: Request):
    return await proxy_request("inside-staging", request)

@app.websocket("/verbal-staging/_stcore/stream")
async def verbal_staging_ws(websocket: WebSocket):
    await proxy_websocket(websocket, "inside-staging", "/verbal-staging/_stcore/stream")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(environ.get("PORT", 3000)))
