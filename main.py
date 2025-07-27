from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

# Variáveis de ambiente
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-message"

ORACLE_AUTH = os.getenv("ORACLE_AUTH")
WMS_API_BASE = os.getenv("ORACLE_API_URL")

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()

    # Log do conteúdo completo recebido no webhook
    print("📥 Payload recebido:", body)

    # Tenta extrair mensagem e número
    message_data = body.get("message", {})
    message = message_data.get("text", "").lower()
    phone = message_data.get("from", "")

    if not message or not phone:
        print("❌ Mensagem ou telefone não encontrados no payload recebido.")
        return {"status": "ignored"}

    print(f"📩 Mensagem recebida de {phone}: {message}")

    if "saldo" in message:
        item_code = message.replace("saldo", "").strip()

        headers = {
            "Authorization": ORACLE_AUTH,
            "Content-Type": "application/json"
        }

        params = {
            "item_id__code": item_code
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(WMS_API_BASE, params=params, headers=headers)
                data = response.json()
                print("🔎 Resposta da API do WMS:", data)
        except Exception as e:
            error_msg = f"❌ Erro ao consultar o WMS: {str(e)}"
            print(error_msg)
            await httpx.post(ZAPI_URL, json={
                "phone": phone,
                "message": error_msg
            })
            return {"status": "error"}

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

        send_payload = {
            "phone": phone,
            "message": reply
        }

        print("📤 Enviando para Z-API:", send_payload)

        async with httpx.AsyncClient() as client:
            zapi_response = await client.post(ZAPI_URL, json=send_payload)
            print("📨 Resposta da Z-API:", zapi_response.status_code, zapi_response.text)

    return {"status": "ok"}
