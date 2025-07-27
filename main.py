import os
import json
from fastapi import FastAPI, Request
import httpx
from dotenv import load_dotenv

# Carrega variáveis do .env se estiver rodando localmente
load_dotenv()

# Inicializa o app FastAPI
app = FastAPI()

# Lê as variáveis de ambiente (segredos e configurações)
ORACLE_API_URL = os.getenv("ORACLE_API_URL")  # URL da API do Oracle WMS
ORACLE_AUTH = os.getenv("ORACLE_AUTH")        # Autenticação Basic do Oracle WMS

ZAPI_URL = f"https://api.z-api.io/instances/{os.getenv('ZAPI_INSTANCE_ID')}/token/{os.getenv('ZAPI_TOKEN')}/send-text"
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")  # Token do cliente Z-API

# Função auxiliar para consultar o Oracle WMS
async def consultar_oracle_wms(item: str):
    params = {
        "q": f"item_id eq '{item}'"
    }

    headers = {
        "Authorization": ORACLE_AUTH,
        "Accept": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(ORACLE_API_URL, params=params, headers=headers)
        print("🔍 Resposta da API do WMS:", response.status_code, response.text)

        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if items:
                # Retorna o saldo (curr_qty) do primeiro resultado
                return items[0].get("curr_qty", "Saldo não encontrado")
        return "❌ Nenhum saldo encontrado para o item."

# Rota para o webhook (ponto de entrada das mensagens do WhatsApp)
@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    print("📥 Payload recebido:", json.dumps(payload, indent=2))

    # Tenta extrair o telefone e o texto da mensagem
    try:
        phone = payload["phone"]
        message = payload["message"]["text"].get("body", "").strip().lower()
    except Exception as e:
        print("❌ Erro ao extrair dados do payload:", str(e))
        return {"status": "error", "detail": "Invalid payload format"}

    # Se a mensagem começar com "saldo", tratamos como consulta
    if message.startswith("saldo"):
        partes = message.split()
        if len(partes) == 2:
            item_id = partes[1]
            saldo = await consultar_oracle_wms(item_id)
            reply = f"📦 Saldo para o item {item_id}: {saldo}"
        else:
            reply = "⚠️ Formato inválido. Use: saldo <item>"
    else:
        reply = "🤖 Comando não reconhecido. Use: saldo <item> para consultar o estoque."

    # Monta o payload e headers para envio via Z-API
    send_payload = {
        "phone": phone,
        "message": reply
    }

    headers = {
        "Client-Token": ZAPI_CLIENT_TOKEN
    }

    # Envia a resposta via WhatsApp usando a Z-API
    async with httpx.AsyncClient() as client:
        zapi_response = await client.post(ZAPI_URL, json=send_payload, headers=headers)
        print("📨 Resposta da Z-API:", zapi_response.status_code, zapi_response.text)

    return {"status": "ok"}
