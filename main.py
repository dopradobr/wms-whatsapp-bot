from fastapi import FastAPI, Request
import httpx
import os
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ===========================================
# 🔐 Environment Variables
# ===========================================
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")

ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

ZAPI_BASE_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

# ===========================================
# Usuários ativos
# ===========================================
activated_users = {}

# ===========================================
# 📤 Envia mensagem de texto
# ===========================================
async def send_message(phone: str, message: str):
    url = f"{ZAPI_BASE_URL}/send-text"
    headers = {"Content-Type": "application/json", "client-token": ZAPI_CLIENT_TOKEN}
    payload = {"phone": phone, "message": message}
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, headers=headers, json=payload)

# ===========================================
# 📤 Envia menu interativo
# ===========================================
async def send_menu(phone: str):
    url = f"{ZAPI_BASE_URL}/send-button-list"
    headers = {"Content-Type": "application/json", "client-token": ZAPI_CLIENT_TOKEN}
    payload = {
        "phone": phone,
        "message": "✅ Consulta WMS ativada!\nEscolha uma das opções abaixo:",
        "footer": "Optivance WMS Bot",
        "buttonText": "📋 Menu",
        "sections": [
            {
                "title": "📦 Consultas WMS",
                "rows": [
                    {"id": "cmd_lpn", "title": "📦 LPN Receiving", "description": "Listar LPNs recebidos"},
                    {"id": "cmd_stored", "title": "🏷 Stored Items", "description": "Itens armazenados"},
                    {"id": "cmd_balance", "title": "📊 Balance WMS", "description": "Consultar saldo de um item"},
                    {"id": "cmd_location", "title": "📍 Items by Location", "description": "Itens por localização"}
                ]
            }
        ]
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, headers=headers, json=payload)

# ===========================================
# Consultas WMS
# ===========================================
async def query_lpn_receiving():
    url = f"{ORACLE_API_URL}&container_id__status_id__description=Received"
    headers = {"Authorization": ORACLE_AUTH}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
    data = r.json().get("results", [])
    if not data:
        return "📦 No LPNs in Receiving."
    return "\n".join([f"• LPN: `{r.get('container_id__container_nbr')}` | Qty: *{r.get('curr_qty')}* | Item: {r.get('item_id__code')}" for r in data])

async def query_stored_items():
    url = f"{ORACLE_API_URL}&container_id__status_id__description=Located"
    headers = {"Authorization": ORACLE_AUTH}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
    data = r.json().get("results", [])
    if not data:
        return "📦 No stored items found."
    data_sorted = sorted(data, key=lambda x: x.get("container_id__curr_location_id__locn_str", ""))
    return "\n".join([f"• Item: `{r.get('item_id__code')}` | Qty: *{r.get('curr_qty')}* | 📍 {r.get('container_id__curr_location_id__locn_str')}" for r in data_sorted])

async def query_item_balance(item: str):
    url = f"{ORACLE_API_URL}&item_id__code={item}"
    headers = {"Authorization": ORACLE_AUTH}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
    data = r.json().get("results", [])
    if not data:
        return f"❌ No balance found for item {item}."
    return f"📊 Balance for {item}: {len(data)} registros"

async def query_items_by_location(location: str):
    url = f"{ORACLE_API_URL}&location_id__locn_str={location}"
    headers = {"Authorization": ORACLE_AUTH}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
    data = r.json().get("results", [])
    if not data:
        return f"📍 No items found at location {location}."
    return "\n".join([f"• Item: `{r.get('item_id__code')}` | LPN: `{r.get('container_id__container_nbr')}` | Qty: *{r.get('curr_qty')}*" for r in data])

# ===========================================
# Webhook
# ===========================================
@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    phone = payload.get("phone")
    text = payload.get("text", {}).get("message", "").strip().lower()
    button_id = payload.get("button", {}).get("id") or payload.get("listResponse", {}).get("rowId")

    # Ativa bot
    if phone not in activated_users:
        if text == "consulta o wms":
            activated_users[phone] = True
            await send_menu(phone)
        return {"status": "ok"}

    # Trata clique no menu
    if button_id:
        if button_id == "cmd_lpn":
            resp = await query_lpn_receiving()
        elif button_id == "cmd_stored":
            resp = await query_stored_items()
        elif button_id == "cmd_balance":
            await send_message(phone, "Digite: item ITEMCODE")
            return {"status": "ok"}
        elif button_id == "cmd_location":
            await send_message(phone, "Digite: loc LOCATIONCODE")
            return {"status": "ok"}
        else:
            resp = "❌ Opção inválida."
        await send_message(phone, resp)
        return {"status": "ok"}

    # Trata respostas de item/location
    if text.startswith("item "):
        code = text.split("item ", 1)[1].strip().upper()
        resp = await query_item_balance(code)
        await send_message(phone, resp)
        return {"status": "ok"}

    if text.startswith("loc "):
        loc = text.split("loc ", 1)[1].strip().upper()
        resp = await query_items_by_location(loc)
        await send_message(phone, resp)
        return {"status": "ok"}

    return {"status": "ok"}
