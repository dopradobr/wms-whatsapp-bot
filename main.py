from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-message"

ORACLE_AUTH = os.getenv("ORACLE_AUTH")
WMS_API_BASE = os.getenv("ORACLE_API_URL")

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    print("📥 Payload recebido:", body)

    # Verifica se veio de fora (mensagem recebida, não enviada pela própria API)
    if not body.get("fromApi", True):
        message_text = body.get("text", {}).get("message", "").lower().strip()
        phone = body.get("phone", "").strip()

        print(f"📩 Mensagem recebida de {phone}: {message_text}")
        print("📞 Formato do número:", repr(phone))

        if not message_text or not phone:
            print("❌ Mensagem ou telefone não encontrados no payload recebido.")
            return {"status": "ignored"}

        # Verifica formato do número
        if not phone.startswith("55") or len(phone) < 12:
            print("❌ Número de telefone inválido:", phone)
            return {"status": "ignored"}

        if "saldo" in message_text:
            item_code = message_text.replace("saldo", "").strip()

            if not item_code:
                reply = "❗ Você precisa informar o código do item após a palavra 'saldo'. Exemplo: saldo 12345"
            else:
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
                    reply = f"❌ Erro ao consultar o WMS: {str(e)}"
                    print(reply)
                    data = None

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
                elif data is not None:
                    reply = f"❌ Nenhum saldo encontrado para o item {item_code}."

            # Enviar mensagem para o WhatsApp via Z-API
            send_payload = {
                "phone": phone,
                "message": reply
            }

            print("📤 Enviando para Z-API:", send_payload)

            zapi_headers = {"Content-Type": "application/json"}

            async with httpx.AsyncClient() as client:
                zapi_response = await client.post(ZAPI_URL, json=send_payload, headers=zapi_headers)
                print("📨 Resposta da Z-API:", zapi_response.status_code, zapi_response.text)

    return {"status": "ok"}
