from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

ZAPI_URL = f"https://api.z-api.io/instances/{os.getenv('ZAPI_INSTANCE_ID')}/token/{os.getenv('ZAPI_TOKEN')}/send-message"
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")  # Pode ser token ou basic auth

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    message = body.get("message", {}).get("text", "").lower()
    phone = body.get("message", {}).get("from", "")

    if not message or not phone:
        return {"status": "ignored"}

    if "saldo" in message:
        item_code = message.replace("saldo", "").strip().upper()

        headers = {
            "Authorization": ORACLE_AUTH,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            r = await client.get(f"{ORACLE_API_URL}?item={item_code}", headers=headers)
            data = r.json()

        if data.get("items"):
            item = data["items"][0]
            qty = item["qty"]
            loc = item.get("loc", "não informada")
            reply = f"📦 Produto: {item_code}\n✅ Quantidade: {qty}\n📍 Local: {loc}"
        else:
            reply = f"❌ Produto {item_code} não encontrado."

        await httpx.post(ZAPI_URL, json={
            "phone": phone,
            "message": reply
        })

    return {"status": "ok"}
