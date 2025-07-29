import os
import requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import uvicorn

# Carregar variáveis de ambiente
load_dotenv()

# Variáveis de ambiente
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")

# URL base da Z-API
ZAPI_BASE_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

app = FastAPI()

# Estado do usuário (para saber se está aguardando o item)
user_state = {}

# Função para enviar mensagem no WhatsApp
def send_whatsapp_message(phone: str, message: str):
    payload = {
        "phone": phone,
        "message": message
    }
    requests.post(f"{ZAPI_BASE_URL}/send-text", json=payload)

# Função para enviar botões no WhatsApp
def send_whatsapp_buttons(phone: str, message: str, buttons: list):
    payload = {
        "phone": phone,
        "message": message,
        "buttons": [{"id": str(i+1), "text": btn} for i, btn in enumerate(buttons)]
    }
    requests.post(f"{ZAPI_BASE_URL}/send-buttons", json=payload)

# Função para consultar o Oracle WMS
def consultar_oracle(filtro_item=None, somente_recebimento=False, enderecado=False):
    try:
        url = ORACLE_API_URL
        if filtro_item:
            url += f"&item_id__code={filtro_item}"
        headers = {
            "Authorization": ORACLE_AUTH
        }
        response = requests.get(url, headers=headers)
        data = response.json()

        located = []
        received = []
        total_located = 0
        total_received = 0

        for item in data.get("items", []):
            status = item.get("container_id__status_id__description", "")
            lpn = item.get("container_id__container_nbr", "-")
            qty = item.get("curr_qty", 0)
            endereco = item.get("location_id__locn_str", "-")

            if status == "Located":
                total_located += qty
                located.append(f"- LPN: {lpn} | Qtd: {qty}" + (f" | 📍 {endereco}" if enderecado else ""))
            elif status == "Received":
                total_received += qty
                received.append(f"- LPN: {lpn} | Qtd: {qty}" + (f" | 📍 {endereco}" if enderecado else ""))

        # Montar resposta
        if somente_recebimento:
            if not received:
                return "📦 Nenhuma LPN encontrada no recebimento."
            return "📦 LPNs no recebimento:\n" + "\n".join(received)

        resposta = f"📦 Saldo para o item: {filtro_item if filtro_item else 'Todos'}\n\n"
        if located:
            resposta += "🔹 Located (Pronto para uso)\n" + "\n".join(located) + "\n\n"
        if received:
            resposta += "🔸 Received (Ainda em recebimento)\n" + "\n".join(received) + "\n\n"
        resposta += f"📊 Total localizado: {total_located}\n📊 Total recebido: {total_received}"

        return resposta.strip()
    except Exception as e:
        return f"⚠️ Erro ao consultar Oracle WMS: {str(e)}"

# Webhook para receber mensagens
@app.post("/webhook")
async def webhook(request: Request):
    try:
        # Tenta pegar como JSON
        try:
            data = await request.json()
        except:
            # Se não for JSON, tenta pegar como form-urlencoded
            form_data = await request.form()
            data = dict(form_data)

        phone = data.get("phone", "")
        message = data.get("message", "").strip()

        # Se o usuário pedir para iniciar o menu
        if message.lower() == "consultar ambiente tpi":
            send_whatsapp_buttons(phone, "Escolha uma opção para consultar:", [
                "Saldo no recebimento",
                "Saldo de um item",
                "Saldo de um item endereçado"
            ])
            return JSONResponse(content={"status": "ok"})

        # Lógica para cada opção
        if message == "Saldo no recebimento":
            resposta = consultar_oracle(somente_recebimento=True)
            send_whatsapp_message(phone, resposta)
            return JSONResponse(content={"status": "ok"})

        if message == "Saldo de um item":
            user_state[phone] = {"acao": "saldo_item"}
            send_whatsapp_message(phone, "🔍 Informe o código do item que deseja consultar:")
            return JSONResponse(content={"status": "ok"})

        if message == "Saldo de um item endereçado":
            user_state[phone] = {"acao": "saldo_item_enderecado"}
            send_whatsapp_message(phone, "🔍 Informe o código do item que deseja consultar com endereços:")
            return JSONResponse(content={"status": "ok"})

        # Quando o usuário está no estado de digitar o item
        if phone in user_state:
            acao = user_state[phone]["acao"]
            if acao == "saldo_item":
                resposta = consultar_oracle(filtro_item=message)
                send_whatsapp_message(phone, resposta)
            elif acao == "saldo_item_enderecado":
                resposta = consultar_oracle(filtro_item=message, enderecado=True)
                send_whatsapp_message(phone, resposta)
            del user_state[phone]
            return JSONResponse(content={"status": "ok"})

        return JSONResponse(content={"status": "ignorado"})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
