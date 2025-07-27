from fastapi import FastAPI, Request
import httpx
import os
import logging

app = FastAPI()

# Configura o logger
logging.basicConfig(level=logging.INFO)

# Variáveis de ambiente (definidas no Render)
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

# URL base da API da Z-API
ZAPI_BASE_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

# Função para enviar mensagem pelo WhatsApp via Z-API
async def enviar_mensagem(numero: str, mensagem: str):
    url = f"{ZAPI_BASE_URL}/send-text"
    headers = {
        "Content-Type": "application/json",
        "client-token": ZAPI_CLIENT_TOKEN  # Header exigido pela Z-API
    }
    payload = {
        "phone": numero,
        "message": mensagem
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        logging.info(f"Resposta da Z-API: {response.status_code} - {response.text}")

# Função para consultar o saldo no Oracle WMS
async def consultar_saldo(item: str):
    url = f"{ORACLE_API_URL}&item_id={item}"
    headers = {
        "Authorization": ORACLE_AUTH
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data["count"] > 0:
                # Somar todas as quantidades
                total = sum([float(i.get("curr_qty", 0)) for i in data["items"]])
                return f"Saldo atual do item {item}: {total}"
            else:
                return f"Nenhum saldo encontrado para o item {item}."
        else:
            return f"Erro ao consultar o saldo. Código: {response.status_code}"

# Rota de Webhook do WhatsApp (Z-API envia as mensagens recebidas aqui)
@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    logging.info(f"Payload recebido: {payload}")

    try:
        # Extrai o número e mensagem
        numero = payload["phone"]
        texto = payload["text"]["message"]

        # Verifica se é uma consulta de saldo
        if texto.lower().startswith("saldo "):
            item = texto.split(" ", 1)[1].strip()
            resposta = await consultar_saldo(item)
        else:
            resposta = "Comando não reconhecido. Envie por exemplo: saldo TEST123"

        await enviar_mensagem(numero, resposta)

    except Exception as e:
        logging.error(f"Erro ao processar a mensagem: {str(e)}")
        return {"error": "Erro ao processar"}

    return {"status": "ok"}
