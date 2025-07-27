from fastapi import FastAPI, Request
import httpx
import os
import logging

# Inicializa a aplicação FastAPI e configura o logger
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# 🔐 Carrega variáveis de ambiente da Render (configuradas no painel)
ORACLE_API_URL = os.getenv("ORACLE_API_URL")
ORACLE_AUTH = os.getenv("ORACLE_AUTH")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

# 🔗 Monta a URL base da Z-API com instance e token
ZAPI_BASE_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

# 📤 Função para enviar mensagens via Z-API (WhatsApp)
async def enviar_mensagem(numero: str, mensagem: str):
    url = f"{ZAPI_BASE_URL}/send-text"
    headers = {
        "Content-Type": "application/json",
        "client-token": ZAPI_CLIENT_TOKEN  # Cabeçalho obrigatório
    }
    payload = {
        "phone": numero,
        "message": mensagem
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        logging.info(f"📨 Resposta da Z-API: {response.status_code} - {response.text}")

# 🔍 Função para consultar o saldo no Oracle WMS com formatação personalizada
async def consultar_saldo(item: str):
    url = f"{ORACLE_API_URL}&item_id__code={item}"
    headers = {
        "Authorization": ORACLE_AUTH
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

        if response.status_code != 200:
            return f"❌ Erro ao consultar o saldo. Código: {response.status_code}"

        data = response.json()
        registros = data.get("results", [])

        if not registros:
            return f"❌ Nenhum saldo encontrado para o item {item}."

        total = sum(float(r.get("curr_qty", 0)) for r in registros)
        qtd_registros = len(registros)
        status_geral = registros[0].get("container_id__status_id__description", "—")

        # Cabeçalho
        resposta = [
            f"📦 *Saldo encontrado para o item* `{item}`",
            f"📄 *Status:* `{status_geral}`",
            f"🔢 *Registros:* {qtd_registros}",
            f"📊 *Total:* **{total:.2f} unidades**",
            "",
            "🔍 *Detalhamento:*"
        ]

        # Linhas detalhadas
        for i, r in enumerate(registros[:20], start=1):  # Limite de até 20 registros
            cod = r.get("item_id__code", "—")
            lpn = r.get("container_id__container_nbr", "—")
            qtd = r.get("curr_qty", 0)
            loc = r.get("location_id__locn_str", "")
            status = r.get("container_id__status_id__description", "").lower()

            linha = [
                f"{i}️⃣",
                f"🆔 *Item:* `{cod}`",
                f"📦 *LPN:* `{lpn}`",
                f"📥 *Qtd:* `{qtd}`"
            ]
            if status != "received" and loc:
                linha.append(f"📍 *Endereço:* `{loc}`")

            resposta.append("\n".join(linha))

        return "\n\n".join(resposta)


# 📥 Endpoint que recebe mensagens do WhatsApp via webhook
@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    logging.info(f"📥 Payload recebido: {payload}")

    try:
        numero = payload["phone"]
        texto = payload.get("text", {}).get("message", "").strip()
        texto_lower = texto.lower()

        # ✅ Só responde se a mensagem contiver "saldo wms "
        if "saldo wms " in texto_lower:
            # Extrai o valor após "saldo wms " e transforma em MAIÚSCULO
            item_raw = texto_lower.split("saldo wms ", 1)[1].strip()
            item = item_raw.upper()  # Força sempre maiúsculo
            logging.info(f"🔎 Item extraído: {item}")
            resposta = await consultar_saldo(item)
            await enviar_mensagem(numero, resposta)
        else:
            logging.info("❌ Mensagem ignorada. Não contém 'saldo wms '.")

    except Exception as e:
        logging.error(f"❌ Erro ao processar mensagem: {str(e)}")

    return {"status": "ok"}
