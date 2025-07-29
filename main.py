import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json

app = FastAPI()

# Variáveis de ambiente
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_URL = os.getenv("ZAPI_URL")
WMS_API_URL = os.getenv("WMS_API_URL")
WMS_USER = os.getenv("WMS_USER")
WMS_PASSWORD = os.getenv("WMS_PASSWORD")

# Função para enviar mensagem no WhatsApp via Z-API
def send_whatsapp_message(phone: str, message: str, buttons=None):
    url = f"{ZAPI_URL}/message/sendText/{phone}"
    payload = {"phone": phone, "message": message}
    if buttons:
        url = f"{ZAPI_URL}/message/sendButtons/{phone}"
        payload = {"phone": phone, "message": message, "buttons": buttons}
    headers = {"Content-Type": "application/json", "apikey": ZAPI_TOKEN}
    requests.post(url, headers=headers, data=json.dumps(payload))

# Função para autenticar no WMS e buscar dados
def get_wms_data(params):
    session = requests.Session()
    session.auth = (WMS_USER, WMS_PASSWORD)
    response = session.get(WMS_API_URL, params=params)
    return response.json()

@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    # Captura o payload cru enviado pelo Z-API
    try:
        data = await request.json()
    except:
        return JSONResponse(content={"status": "error", "message": "Payload não é JSON"}, status_code=400)

    print("📩 Payload recebido do Z-API:", data)

    # Tentativa de extrair phone e message
    phone = data.get("phone") or data.get("from") or None
    message = data.get("message") or data.get("body") or None

    if not phone or not message:
        return JSONResponse(content={"status": "error", "message": "Campos 'phone' e 'message' não encontrados"}, status_code=400)

    message = message.strip().lower()

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
        data_wms = get_wms_data(params)
        if not data_wms.get("results"):
            send_whatsapp_message(phone, "⚠️ Nenhum LPN encontrado no recebimento.")
            return JSONResponse(content={"status": "ok"})

        msg_lines = ["📦 Saldo no Recebimento:"]
        for r in data_wms["results"]:
            msg_lines.append(f"• LPN: {r['container_id__container_nbr']} | Item: {r['item_id__code']} | Qtd: {int(r['curr_qty'])}")
        msg_lines.append(f"📊 Total de LPNs: {len(data_wms['results'])}")

        send_whatsapp_message(phone, "\n".join(msg_lines))
        return JSONResponse(content={"status": "ok"})

    return JSONResponse(content={"status": "ignored"})
