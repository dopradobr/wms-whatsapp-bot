from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

# Variáveis de ambiente
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")

ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"


# Função para enviar mensagens pelo WhatsApp
async def send_whatsapp_message(phone: str, message: str, buttons=None):
    payload = {"phone": phone, "message": message}
    if buttons:
        payload["buttons"] = buttons

    async with httpx.AsyncClient() as client:
        await client.post(f"{ZAPI_URL}/send-button-message", json=payload)

# Função para buscar dados no Oracle WMS
async def get_oracle_data(query_params=""):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{ORACLE_API_URL}{query_params}",
            headers={"Authorization": ORACLE_AUTH}
        )
        return r.json()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Recebido:", data)

    message = data.get("message", {}).get("text", "").strip()
    phone = data.get("message", {}).get("from", "")

    # Fluxo inicial
    if message.lower() == "consultar ambiente tpi":
        buttons = [
            {"id": "saldo_recebimento", "text": "📦 Saldo no Recebimento"},
            {"id": "saldo_item", "text": "🔍 Saldo de um Item"},
            {"id": "saldo_item_endereco", "text": "📍 Saldo Item Endereçado"}
        ]
        await send_whatsapp_message(phone, "Escolha uma opção:", buttons)
        return {"status": "ok"}

    # Escolha de Saldo no Recebimento
    if message == "saldo_recebimento":
        data = await get_oracle_data("&container_id__status_id__description=Received")
        lpn_list = [item.get("container_id__container_nbr", "") for item in data.get("items", [])]
        resposta = "\n".join(lpn_list) if lpn_list else "Nenhuma LPN encontrada no recebimento."
        await send_whatsapp_message(phone, f"📦 LPNs no recebimento:\n{resposta}")
        return {"status": "ok"}

    # Saldo de um item (solicita digitação)
    if message == "saldo_item":
        await send_whatsapp_message(phone, "Digite o código do item que deseja consultar:")
        return {"status": "ok"}

    if message.startswith("item "):
        codigo = message.replace("item ", "").strip()
        data = await get_oracle_data(f"&item_id__code={codigo}")
        saldo_total = sum([float(item.get("curr_qty", 0)) for item in data.get("items", [])])
        await send_whatsapp_message(phone, f"🔍 Saldo do item {codigo}: {saldo_total}")
        return {"status": "ok"}

    # Saldo Item Endereçado
    if message == "saldo_item_endereco":
        await send_whatsapp_message(phone, "Digite o código do item para consultar LPNs e endereços:")
        return {"status": "ok"}

    if message.startswith("endereco "):
        codigo = message.replace("endereco ", "").strip()
        data = await get_oracle_data(f"&item_id__code={codigo}")
        detalhes = "\n".join([
            f"LPN: {i.get('container_id__container_nbr')} - Endereço: {i.get('location_id__locn_str')}"
            for i in data.get("items", [])
        ])
        await send_whatsapp_message(phone, f"📍 LPNs e endereços do item {codigo}:\n{detalhes}")
        return {"status": "ok"}

    return {"status": "ignorado"}
