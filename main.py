from asyncio import sleep
from temporary_token import Token as TToken
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from backgroundtasks import clean_invalid_tokens as cit
from backgroundtasks import stop_run_continuously
from functools import partial
import schedule
from authenticator import *
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()


class Aluno(BaseModel):
    name: str
    cod: str
    token: str


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


templates = Jinja2Templates(directory="templates")

origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
tokens = {}

@app.on_event("startup")
async def startup_event():
    schedule.every(5).minutes.do(cit,tokens)
@app.on_event("shutdown")
async def shutdown_event():
    stop_run_continuously.set()

@app.get("/",response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("token.html", {"request": request})

@app.get("/temporary-token/secunds={id}")
async def get_token(id: int):
    token = TToken(seconds=id)
    tokens.update(token)
    return str(token)

@app.post("/validar")
async def validar(aluno:Aluno):
    token = tokens.get(aluno.token,TToken(alive=False))
    if token.is_valid():
        tokens.pop(aluno.token)
        return "Operação realizada com sucesso"
    return "Token invalido"

@app.get("/turma/{turma_id}")
async def read_item(turma_id):
    return {"turma_id": turma_id}

@app.get("/login", response_class=HTMLResponse)
async def read_item(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "scopes": form_data.scopes},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@app.get("/users/me/items/")
async def read_own_items(
    current_user: User = Security(get_current_active_user, scopes=["items"])
):
    return [{"item_id": "Foo", "owner": current_user.username}]


@app.get("/status/")
async def read_system_status(current_user: User = Depends(get_current_user)):
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            token = TToken(seconds=3)
            tokens.update(token)
            await websocket.send_text(token.base64_qr_code)
            await sleep(token.duration)
    except Exception as e:
        print(e)
        manager.disconnect(websocket)
