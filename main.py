import os
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import json

app = FastAPI()

# Variáveis de ambiente
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_URL = os.getenv("ZAPI_URL")
WMS_API_URL = os.getenv("WMS_API_URL")
WMS_USER = os.getenv("WMS_USER")
WMS_PASSWORD = os.getenv("WMS_PASSWORD")

# Função para enviar mensagem no WhatsApp via Z-API
def send_whatsapp_message(phone: str, message: str, buttons: Optional[list] = None):
    url = f"{ZAPI_URL}/message/sendText/{phone}"
    payload = {"phone": phone, "message": message}
    if buttons:
        url = f"{ZAPI_URL}/message/sendButtons/{phone}"
        payload = {
            "phone": phone,
            "message": message,
            "buttons": buttons
        }
    headers = {"Content-Type": "application/json", "apikey": ZAPI_TOKEN}
    requests.post(url, headers=headers, data=json.dumps(payload))

# Função para autenticar no WMS e buscar dados
def get_wms_data(params):
    session = requests.Session()
    session.auth = (WMS_USER, WMS_PASSWORD)
    response = session.get(WMS_API_URL, params=params)
    return response.json()

# Modelo para receber mensagens do WhatsApp
class WhatsAppMessage(BaseModel):
    phone: str
    message: str

@app.post("/webhook")
async def whatsapp_webhook(msg: WhatsAppMessage):
    phone = msg.phone
    message = msg.message.strip().lower()

    if message == "consultar ambiente tpi":
        send_whatsapp_message(
            phone,
            "📋 Escolha uma opção abaixo:",
            buttons=[
                {"id": "saldo_recebimento", "label": "📦 Saldo no Recebimento"},
                {"id": "saldo_item", "label": "🔍 Saldo por Item"},
                {"id": "saldo_item_enderecado", "label": "🏷 Saldo por Item Endereçado"}
            ]
        )
        return JSONResponse(content={"status": "ok"})

    elif message == "saldo_recebimento":
        params = {
            "container_id__status_id__description": "Received",
            "values_list": "item_id__code,container_id__container_nbr,curr_qty"
        }
        data = get_wms_data(params)
        if not data["results"]:
            send_whatsapp_message(phone, "⚠️ Nenhum LPN encontrado no recebimento.")
            return JSONResponse(content={"status": "ok"})

        msg_lines = ["📦 Saldo no Recebimento:\n"]
        for r in data["results"]:
            msg_lines.append(f"• LPN: {r['container_id__container_nbr']} | Item: {r['item_id__code']} | Qtd: {int(r['curr_qty'])}")
        msg_lines.append(f"\n📊 Total de LPNs: {len(data['results'])}")

        send_whatsapp_message(phone, "\n".join(msg_lines))
        return JSONResponse(content={"status": "ok"})

    elif message == "saldo_item":
        send_whatsapp_message(phone, "✏️ Digite o código do item para consultar o saldo.")
        return JSONResponse(content={"status": "ok"})

    elif message.startswith("item "):
        item_code = message.replace("item ", "").strip().upper()
        params = {
            "item_id__code": item_code,
            "values_list": "item_id__code,container_id__container_nbr,curr_qty,location_id__locn_str,container_id__status_id__description"
        }
        data = get_wms_data(params)

        if not data["results"]:
            send_whatsapp_message(phone, f"⚠️ Nenhum saldo encontrado para o item {item_code}.")
            return JSONResponse(content={"status": "ok"})

        located = [r for r in data["results"] if r["container_id__status_id__description"] == "Located"]
        received = [r for r in data["results"] if r["container_id__status_id__description"] == "Received"]

        msg_lines = [f"📦 Saldo para o item: {item_code}\n"]
        if located:
            msg_lines.append("🔹 Located (Pronto para uso)")
            for r in located:
                msg_lines.append(f"- LPN: {r['container_id__container_nbr']} | Qtd: {int(r['curr_qty'])} | 📍 Endereço: {r['location_id__locn_str']}")
        if received:
            msg_lines.append("\n🔸 Received (Ainda em recebimento)")
            for r in received:
                msg_lines.append(f"- LPN: {r['container_id__container_nbr']} | Qtd: {int(r['curr_qty'])}")

        msg_lines.append(f"\n📊 Total localizado: {sum(int(r['curr_qty']) for r in located)}")
        msg_lines.append(f"📊 Total recebido: {sum(int(r['curr_qty']) for r in received)}")

        send_whatsapp_message(phone, "\n".join(msg_lines))
        return JSONResponse(content={"status": "ok"})

    elif message == "saldo_item_enderecado":
        send_whatsapp_message(phone, "✏️ Digite o código do item para consultar com endereço.")
        return JSONResponse(content={"status": "ok"})

    elif message.startswith("item_end "):
        item_code = message.replace("item_end ", "").strip().upper()
        params = {
            "item_id__code": item_code,
            "values_list": "item_id__code,container_id__container_nbr,curr_qty,location_id__locn_str"
        }
        data = get_wms_data(params)

        if not data["results"]:
            send_whatsapp_message(phone, f"⚠️ Nenhum saldo encontrado para o item {item_code}.")
            return JSONResponse(content={"status": "ok"})

        msg_lines = [f"🏷 Saldo para o item: {item_code}\n"]
        for r in data["results"]:
            msg_lines.append(f"- LPN: {r['container_id__container_nbr']} | 📍 Endereço: {r['location_id__locn_str']} | Qtd: {int(r['curr_qty'])}")

        send_whatsapp_message(phone, "\n".join(msg_lines))
        return JSONResponse(content={"status": "ok"})

    return JSONResponse(content={"status": "ignored"})
