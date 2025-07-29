import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Optional

# =========================
# CONFIGURAÇÕES DO AMBIENTE
# =========================
ZAPI_URL = os.getenv("ZAPI_URL")  # URL da sua instância Z-API
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")  # Token da sua instância Z-API
WMS_URL = os.getenv("WMS_URL")  # URL base do Oracle WMS Cloud
WMS_LOGIN = os.getenv("WMS_LOGIN")  # Usuário WMS
WMS_PASSWORD = os.getenv("WMS_PASSWORD")  # Senha WMS

# =========================
# APP FASTAPI
# =========================
app = FastAPI()

# Modelo de recebimento de mensagens do WhatsApp
class WhatsAppMessage(BaseModel):
    phone: str
    text: str
    messageId: Optional[str] = None

# Função para enviar mensagem normal no WhatsApp
def send_whatsapp_message(phone, text):
    payload = {"phone": phone, "message": text}
    requests.post(f"{ZAPI_URL}/send-text", headers={"client-token": ZAPI_TOKEN}, json=payload)

# Função para enviar botões no WhatsApp
def send_whatsapp_buttons(phone, body, buttons):
    payload = {
        "phone": phone,
        "message": body,
        "buttons": [{"id": f"btn_{i}", "text": btn} for i, btn in enumerate(buttons, start=1)]
    }
    requests.post(f"{ZAPI_URL}/send-buttons", headers={"client-token": ZAPI_TOKEN}, json=payload)

# Função para consultar saldo no WMS
def consultar_wms(filtro_item=None, enderecado=False, recebimento=False):
    try:
        # Monta query conforme tipo de busca
        url = f"{WMS_URL}?values_list=item_id__code,container_id__container_nbr,location_id__locn_str,container_id__status_id__description,curr_qty"

        if filtro_item:
            url += f"&item_id__code={filtro_item}"

        if recebimento:
            url += "&container_id__status_id__description=Received"

        # Autenticação no WMS
        resp = requests.get(url, auth=(WMS_LOGIN, WMS_PASSWORD))
        resp.raise_for_status()
        data = resp.json()

        if not data.get("results"):
            return "⚠️ Nenhum registro encontrado."

        located = []
        received = []
        for r in data["results"]:
            status = r.get("container_id__status_id__description", "")
            qty = int(r.get("curr_qty", 0))
            lpn = r.get("container_id__container_nbr", "")
            loc = r.get("location_id__locn_str", "")

            if status == "Located":
                if enderecado:
                    located.append(f"- LPN: {lpn} | Qtd: {qty} | 📍 Endereço: {loc}")
                else:
                    located.append(f"- LPN: {lpn} | Qtd: {qty}")
            elif status == "Received":
                received.append(f"- LPN: {lpn} | Qtd: {qty}")

        total_located = sum(int(r.get("curr_qty", 0)) for r in data["results"] if r.get("container_id__status_id__description") == "Located")
        total_received = sum(int(r.get("curr_qty", 0)) for r in data["results"] if r.get("container_id__status_id__description") == "Received")

        resposta = f"📦 Saldo para o item: {filtro_item if filtro_item else 'Todos'}\n\n"
        if located:
            resposta += "🔹 Located (Pronto para uso)\n" + "\n".join(located) + "\n\n"
        if received:
            resposta += "🔸 Received (Ainda em recebimento)\n" + "\n".join(received) + "\n\n"
        resposta += f"📊 Total localizado: {total_located}\n📊 Total recebido: {total_received}"
        return resposta.strip()

    except Exception as e:
        return f"❌ Erro ao consultar WMS: {e}"

# =========================
# FLUXO WHATSAPP
# =========================
@app.post("/webhook")
async def webhook(msg: WhatsAppMessage):
    texto = msg.text.strip()
    phone = msg.phone

    # Se usuário iniciar com comando
    if texto.lower() == "consultar ambiente tpi":
        send_whatsapp_buttons(
            phone,
            "📋 Escolha uma opção:",
            ["📦 Saldo no Recebimento", "🔍 Saldo por Item", "🏷 Saldo por Item Endereçado"]
        )
        return {"status": "menu_enviado"}

    # Opção 1: Saldo no Recebimento
    if texto == "📦 Saldo no Recebimento":
        resposta = consultar_wms(recebimento=True)
        send_whatsapp_message(phone, resposta)
        send_whatsapp_buttons(
            phone,
            "Deseja fazer outra consulta?",
            ["📦 Saldo no Recebimento", "🔍 Saldo por Item", "🏷 Saldo por Item Endereçado"]
        )
        return {"status": "saldo_recebimento"}

    # Opção 2: Saldo por Item (pedir código)
    if texto == "🔍 Saldo por Item":
        send_whatsapp_message(phone, "✏️ Informe o código do item:")
        return {"status": "aguardando_item"}

    # Opção 3: Saldo por Item Endereçado (pedir código)
    if texto == "🏷 Saldo por Item Endereçado":
        send_whatsapp_message(phone, "✏️ Informe o código do item para busca com endereço:")
        return {"status": "aguardando_item_enderecado"}

    # Se usuário enviou código após pedir
    if texto.upper().startswith("ITEM "):
        item_code = texto.replace("ITEM ", "").strip()
        resposta = consultar_wms(filtro_item=item_code)
        send_whatsapp_message(phone, resposta)
        send_whatsapp_buttons(
            phone,
            "Deseja fazer outra consulta?",
            ["📦 Saldo no Recebimento", "🔍 Saldo por Item", "🏷 Saldo por Item Endereçado"]
        )
        return {"status": "item_consultado"}

    if texto.upper().startswith("ENDERECADO "):
        item_code = texto.replace("ENDERECADO ", "").strip()
        resposta = consultar_wms(filtro_item=item_code, enderecado=True)
        send_whatsapp_message(phone, resposta)
        send_whatsapp_buttons(
            phone,
            "Deseja fazer outra consulta?",
            ["📦 Saldo no Recebimento", "🔍 Saldo por Item", "🏷 Saldo por Item Endereçado"]
        )
        return {"status": "item_enderecado_consultado"}

    return {"status": "ignorado"}
