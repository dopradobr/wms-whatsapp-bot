from fastapi import FastAPI, Request
import httpx
import os

# Inicializa a aplicação FastAPI
app = FastAPI()

# ========================
# CONFIGURAÇÕES DO SISTEMA
# ========================

# Variáveis de ambiente para autenticação com a Z-API
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"  # endpoint correto

# Variáveis para autenticação com a API do Oracle WMS Cloud (ou seu sistema de backend)
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
WMS_API_BASE = os.getenv("ORACLE_API_URL")

# ========================
# ENDPOINT PRINCIPAL
# ========================

@app.post("/webhook")
async def receive_message(request: Request):
    """
    Endpoint que recebe as mensagens enviadas para o número do WhatsApp integrado à Z-API.
    Aqui tratamos o payload, extraímos as informações, consultamos o WMS e respondemos pelo WhatsApp.
    """
    body = await request.json()
    print("📥 Payload recebido:", body)

    # Verifica se a mensagem NÃO veio da própria API (ou seja, veio de um usuário real)
    if not body.get("fromApi", True):
        message_text = body.get("text", {}).get("message", "").lower().strip()
        phone = body.get("phone", "")

        # Se mensagem ou telefone não estiverem presentes, ignora
        if not message_text or not phone:
            print("❌ Mensagem ou telefone não encontrados no payload recebido.")
            return {"status": "ignored"}

        print(f"📩 Mensagem recebida de {phone}: {message_text}")

        # Trata comandos com a palavra "saldo"
        if "saldo" in message_text:
            # Extrai o código do item após a palavra "saldo"
            item_code = message_text.replace("saldo", "").strip()

            headers = {
                "Authorization": ORACLE_AUTH,
                "Content-Type": "application/json"
            }
            params = {
                "item_id__code": item_code  # parâmetro da API do WMS
            }

            try:
                # Requisição para a API do WMS consultando saldo do item
                async with httpx.AsyncClient() as client:
                    response = await client.get(WMS_API_BASE, params=params, headers=headers)
                    data = response.json()
                    print("🔎 Resposta da API do WMS:", data)
            except Exception as e:
                error_msg = f"❌ Erro ao consultar o WMS: {str(e)}"
                print(error_msg)
                # Envia mensagem de erro para o WhatsApp
                await httpx.post(ZAPI_URL, json={"phone": phone, "message": error_msg})
                return {"status": "error"}

            # Monta a resposta com base no resultado da API do WMS
            if isinstance(data, list) and len(data) > 0:
                reply_lines = [f"📦 Resultado para o item {item_code}:"]
                for i, item in enumerate(data[:5], start=1):
                    qty = item.get("curr_qty", "0")
                    loc = item.get("location_id__locn_str") or "—"
                    container = item.get("container_id__container_nbr", "—")
                    status = item.get("container_id__status_id__description", "—")
                    reply_lines.append(f"{i}. Qty: {qty} | Loc: {loc} | Ctn: {container} | {status}")
                reply_lines.append("\n📩 Para consultar outro item, envie: saldo [código]")
                reply = "\n".join(reply_lines)
            else:
                reply = f"❌ Nenhum saldo encontrado para o item {item_code}."

            # Monta payload para enviar a resposta via WhatsApp
            send_payload = {
                "phone": phone,
                "message": reply
            }

            print("📤 Enviando para Z-API:", send_payload)

            try:
                async with httpx.AsyncClient() as client:
                    zapi_response = await client.post(ZAPI_URL, json=send_payload)
                    print("📨 Resposta da Z-API:", zapi_response.status_code, zapi_response.text)
            except Exception as e:
                print("❌ Erro ao enviar mensagem para Z-API:", str(e))

    return {"status": "ok"}
