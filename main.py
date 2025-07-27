from fastapi import FastAPI, Request
import httpx
import os
import logging

# Inicializa o app e o logger
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Carrega variáveis de ambiente
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

# Monta a URL base da Z-API
ZAPI_BASE_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

# 🔁 Função para enviar mensagem no WhatsApp via Z-API
async def enviar_mensagem(numero: str, mensagem: str):
    url = f"{ZAPI_BASE_URL}/send-text"
    headers = {
        "Content-Type": "application/json",
        "client-token": ZAPI_CLIENT_TOKEN
    }
    payload = {
        "phone": numero,
        "message": mensagem
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        logging.info(f"📨 Resposta da Z-API: {response.status_code} - {response.text}")

# 🔍 Função para consultar o saldo no Oracle WMS
async def consultar_saldo(item: str):
    url = f"{ORACLE_API_URL}&item_id__code={item}"
    headers = {
        "Authorization": ORACLE_AUTH
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("count", 0) > 0:
                total = sum([float(i.get("curr_qty", 0)) for i in data.get("items", [])])
                return f"📦 Saldo do item {item}: {total}"
            else:
                return f"❌ Nenhum saldo encontrado para o item {item}."
        else:
            return f"❌ Erro ao consultar o saldo. Código: {response.status_code}"

# 📥 Rota principal de entrada de mensagens via webhook do WhatsApp
@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    logging.info(f"📥 Payload recebido: {payload}")

    try:
        numero = payload["phone"]
        texto = payload.get("text", {}).get("message", "").strip()
        texto_lower = texto.lower()

        # ✅ Responde apenas se a mensagem contiver "saldo "
        if "saldo wms " in texto_lower:
            item = texto_lower.split("saldo wms ", 1)[1].strip()
            resposta = await consultar_saldo(item)
            await enviar_mensagem(numero, resposta)
        else:
            logging.info("❌ Mensagem ignorada. Não contém 'saldo wms '.")

    except Exception as e:
        logging.error(f"❌ Erro ao processar mensagem: {str(e)}")

    return {"status": "ok"}
