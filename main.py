from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

# URLs e tokens da Z-API e Oracle
ZAPI_URL = f"https://api.z-api.io/instances/{os.getenv('ZAPI_INSTANCE_ID')}/token/{os.getenv('ZAPI_TOKEN')}/send-message"
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
WMS_API_BASE = "https://ta32.wms.ocs.oraclecloud.com/redwoodlogistics_test/wms/lgfapi/v10/entity/inventory"

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    message = body.get("message", {}).get("text", "").lower()
    phone = body.get("message", {}).get("from", "")

    if not message or not phone:
        return {"status": "ignored"}

    if "saldo" in message:
        item_code = message.replace("saldo", "").strip()

        # Parâmetros da API Oracle
        params = {
            "item_id__code": item_code,
            "container_id__status_id__description": ["Located", "Received"],
            "values_list": (
                "id,item_id__code,location_id__locn_str,"
                "invn_attr_id__invn_attr_a,container_id__container_nbr,"
                "batch_number_id__batch_nbr,container_id__status_id__description,curr_qty"
            )
        }

        headers = {
            "Authorization": ORACLE_AUTH,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(WMS_API_BASE, params=params, headers=headers)
                data = r.json()
            except Exception as e:
                await httpx.post(ZAPI_URL, json={
                    "phone": phone,
                    "message": f"❌ Erro ao consultar o WMS: {str(e)}"
                })
                return {"status": "error"}

        # Montar resposta
        if isinstance(data, list) and len(data) > 0:
            reply_lines = [f"📦 Resultado para o item {item_code}:"]
            for i, item in enumerate(data[:5], start=1):  # Limita a 5 resultados
                qty = item.get("curr_qty", "0")
                loc = item.get("location_id__locn_str") or "—"
                container = item.get("container_id__container_nbr", "—")
                status = item.get("container_id__status_id__description", "—")
                reply_lines.append(f"{i}. Qty: {qty} | Loc: {loc} | Ctn: {container} | {status}")

            reply_lines.append("\n📩 Para consultar outro item, envie: saldo [código]")
            reply = "\n".join(reply_lines)
        else:
            reply = f"❌ Nenhum saldo encontrado para o item {item_code}."

        # Enviar resposta via Z-API (WhatsApp)
        await httpx.post(ZAPI_URL, json={
            "phone": phone,
            "message": reply
        })

    return {"status": "ok"}

