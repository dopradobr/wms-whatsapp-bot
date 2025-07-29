
import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

# Variáveis de ambiente
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")

# Função para enviar mensagem no WhatsApp
def send_whatsapp_message(phone, message, buttons=None):
    if buttons:
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-button-message"
        payload = {
            "phone": phone,
            "message": message,
            "buttons": buttons
        }
    else:
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        payload = {
            "phone": phone,
            "message": message
        }

    headers = {"Client-Token": ZAPI_CLIENT_TOKEN}
    requests.post(url, json=payload, headers=headers)

# Função para consultar saldo no recebimento
def consultar_lpn_recebimento():
    resp = requests.get(ORACLE_API_URL, headers={"Authorization": ORACLE_AUTH})
    if resp.status_code != 200:
        return "Erro ao consultar Oracle WMS."
    data = resp.json().get("items", [])
    lpns = [item["container_id__container_nbr"] for item in data if item.get("container_id__status_id__description") == "Received"]
    return "\n".join(lpns) if lpns else "Nenhuma LPN encontrada no recebimento."

# Função para consultar saldo de um item
def consultar_saldo_item(item_code, enderecado=False):
    resp = requests.get(ORACLE_API_URL, headers={"Authorization": ORACLE_AUTH})
    if resp.status_code != 200:
        return "Erro ao consultar Oracle WMS."
    data = resp.json().get("items", [])
    resultados = []
    for item in data:
        if item.get("item_id__code") == item_code:
            if enderecado:
                resultados.append(f"{item['container_id__container_nbr']} - {item['location_id__locn_str']}")
            else:
                resultados.append(f"LPN: {item['container_id__container_nbr']} - Qtd: {item['curr_qty']}")
    return "\n".join(resultados) if resultados else "Nenhum saldo encontrado para este item."

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    phone = data.get("phone")
    text = data.get("message", "").strip()

    # Início do fluxo
    if text.lower() == "consultar ambiente tpi":
        send_whatsapp_message(phone, "Escolha uma das opções abaixo:", buttons=[
            {"id": "saldo_recebimento", "label": "Saldo no Recebimento"},
            {"id": "saldo_item", "label": "Saldo Item"},
            {"id": "saldo_item_end", "label": "Saldo Item Endereçado"}
        ])
        return {"status": "ok"}

    # Botão 1 - Saldo no recebimento
    if text == "saldo_recebimento":
        resultado = consultar_lpn_recebimento()
        send_whatsapp_message(phone, resultado)
        return {"status": "ok"}

    # Botão 2 - Saldo de item (solicitar código)
    if text == "saldo_item":
        send_whatsapp_message(phone, "Por favor, digite o código do item:")
        return {"status": "ok"}

    # Botão 3 - Saldo de item endereçado (solicitar código)
    if text == "saldo_item_end":
        send_whatsapp_message(phone, "Por favor, digite o código do item para consulta endereçada:")
        return {"status": "ok"}

    # Caso tenha digitado código do item
    if len(text) >= 3 and text.isalnum():
        resultado = consultar_saldo_item(text, enderecado=False)
        send_whatsapp_message(phone, resultado)
        return {"status": "ok"}

    return {"status": "ignored"}
