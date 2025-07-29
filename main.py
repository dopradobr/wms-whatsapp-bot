from fastapi import FastAPI, Request
import requests
import threading
import os

app = FastAPI()

ZAPI_URL = os.getenv("ZAPI_URL", "https://api.z-api.io/instances/YOUR_INSTANCE/token/YOUR_TOKEN/send-text")
ZAPI_INSTANCE_TOKEN = os.getenv("ZAPI_INSTANCE_TOKEN", "YOUR_INSTANCE_TOKEN")
ZAPI_API_TOKEN = os.getenv("ZAPI_API_TOKEN", "YOUR_API_TOKEN")

# Função para enviar mensagem no WhatsApp
def send_message(phone: str, text: str):
    payload = {
        "phone": phone,
        "message": text
    }
    headers = {
        "Client-Token": ZAPI_API_TOKEN
    }
    try:
        r = requests.post(ZAPI_URL, json=payload, headers=headers)
        print("Resposta Z-API:", r.status_code, r.text)
    except Exception as e:
        print("Erro ao enviar mensagem:", e)

# Função para processar consulta no Oracle WMS Cloud
def consultar_wms(phone: str, mensagem: str):
    try:
        # Aqui você coloca a lógica de integração real com Oracle WMS Cloud
        resultado = f"📦 Resultado fictício para: {mensagem}"  
        send_message(phone, resultado)
    except Exception as e:
        send_message(phone, f"❌ Erro ao consultar: {str(e)}")

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print("Payload recebido:", data)

    try:
        mensagem = data.get("text", {}).get("message", "").strip()
        telefone = data.get("phone", "")

        if mensagem:
            # Responde imediatamente para evitar timeout
            send_message(telefone, "✅ Solicitação recebida! Processando...")

            # Processa em segundo plano
            threading.Thread(target=consultar_wms, args=(telefone, mensagem)).start()

    except Exception as e:
        print("Erro no webhook:", e)

    return {"status": "ok"}
