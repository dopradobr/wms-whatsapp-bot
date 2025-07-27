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
# 🔍 Função para consultar saldo de um item no Oracle WMS Cloud
async def consultar_saldo(item: str):
    # Monta a URL da API com o código do item como parâmetro
    url = f"{ORACLE_API_URL}&item_id__code={item}"
    
    # Define o cabeçalho com a autorização do Oracle WMS
    headers = {
        "Authorization": ORACLE_AUTH
    }

    # Inicia a requisição HTTP assíncrona
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

        # Se a resposta for OK (200), processa os dados
        if response.status_code == 200:
            data = response.json()

            # Extrai a lista de resultados
            resultados = data.get("results", [])

            # Se não houver resultados, informa ao usuário
            if not resultados:
                return f"❌ Nenhum saldo encontrado para o item {item}."

            # Ordena os resultados por status (ex: Received, Located)
            resultados.sort(key=lambda x: x.get("container_id__status_id__description", "").lower())

            # Calcula o total de quantidades somando os campos curr_qty
            total = sum([float(i.get("curr_qty", 0)) for i in resultados])
            total = int(total)  # Remove casas decimais para visualização no WhatsApp

            # Extrai e organiza os diferentes status encontrados
            status_set = set(i.get("container_id__status_id__description", "—") for i in resultados)
            status_text = " / ".join(sorted(status_set))

            # Inicia a resposta formatada com resumo geral
            resposta = [
                f"📦 Saldo encontrado para o item: {item}",
                f"📄 Status: {status_text}",
                f"🔢 Registros: {len(resultados)}",
                f"📊 Total: {total} unidades",
                "",
                "*Detalhamento:*"
            ]

            # Itera sobre cada registro e monta o detalhamento
            for idx, r in enumerate(resultados, start=1):
                lpn = r.get("container_id__container_nbr", "—")  # LPN (número do contêiner)
                qtd = int(float(r.get("curr_qty", 0)))            # Quantidade, sem decimais
                status = r.get("container_id__status_id__description", "")  # Status (ex: Received)
                endereco = r.get("location_id__locn_str", "").strip()       # Endereço (quando aplicável)

                # Monta os detalhes do registro
                detalhe = [
                    f"{idx}.",                  # Número sequencial
                    f"📦 LPN: {lpn}",            # LPN do item
                    f"📥 Qtd: {qtd}"             # Quantidade
                ]

                # Adiciona endereço apenas se o status NÃO for "Received"
                if status.lower() != "received":
                    detalhe.append(f"📍 Endereço: {endereco or '—'}")

                # Junta os detalhes e adiciona à resposta final
                resposta.append("\n".join(detalhe))

            # Junta todas as linhas com espaçamento e retorna
            return "\n\n".join(resposta)

        else:
            # Caso a resposta não seja 200, retorna o erro HTTP
            return f"❌ Erro ao consultar o saldo. Código: {response.status_code}"


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
