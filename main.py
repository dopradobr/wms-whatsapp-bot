import httpx
import os
import logging
from fastapi import FastAPI, Request, HTTPException
from pydantic_settings import BaseSettings # ALTERADO: Importado de pydantic_settings
from pydantic import Field, ValidationError

# ========================
# CONFIGURAÇÃO DE LOGGING
# ========================
# Configura um logger para registrar eventos da aplicação, o que é melhor que usar print()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ========================
# CONFIGURAÇÕES DO SISTEMA COM PYDANTIC
# ========================
# Utiliza Pydantic para carregar e validar as variáveis de ambiente.
# Se alguma variável essencial não for definida, a aplicação não iniciará.
class Settings(BaseSettings):
    zapi_instance_id: str = Field(..., env="ZAPI_INSTANCE_ID")
    zapi_token: str = Field(..., env="ZAPI_TOKEN")
    oracle_auth: str = Field(..., env="ORACLE_AUTH")
    wms_api_base: str = Field(..., env="ORACLE_API_URL")

    @property
    def zapi_url(self) -> str:
        """Endpoint para envio de mensagens de texto da Z-API."""
        return f"https://api.z-api.io/instances/{self.zapi_instance_id}/token/{self.zapi_token}/send-text"

    class Config:
        # Permite carregar variáveis de um arquivo .env para desenvolvimento local
        env_file = ".env"
        env_file_encoding = "utf-8"

try:
    settings = Settings()
except ValidationError as e:
    logger.critical(f"Erro de validação nas variáveis de ambiente: {e}")
    # Se as configurações não puderem ser carregadas, a aplicação não deve continuar.
    exit()


# Inicializa a aplicação FastAPI
app = FastAPI(
    title="WhatsApp WMS Bot",
    description="Webhook para integrar WhatsApp com Oracle WMS via Z-API",
    version="1.0.0"
)

# ========================
# FUNÇÕES AUXILIARES
# ========================

async def query_wms_for_stock(item_code: str) -> list | None:
    """
    Consulta a API do WMS para obter o saldo de um item específico.

    Args:
        item_code: O código do item a ser consultado.

    Returns:
        Uma lista com os dados do saldo se a consulta for bem-sucedida, None caso contrário.
    """
    headers = {
        "Authorization": settings.oracle_auth,
        "Content-Type": "application/json"
    }
    params = {
        "item_id__code": item_code
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.wms_api_base, params=params, headers=headers)
            response.raise_for_status()  # Lança uma exceção para respostas com código de erro (4xx ou 5xx)
            data = response.json()
            logger.info(f"Resposta recebida da API do WMS para o item '{item_code}': {data}")
            return data
    except httpx.RequestError as e:
        logger.error(f"Erro de rede ao consultar o WMS para o item '{item_code}': {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Erro de status HTTP ao consultar o WMS: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"Erro inesperado ao consultar o WMS: {e}")
    
    return None

def format_stock_reply(data: list, item_code: str) -> str:
    """
    Formata a resposta de saldo para ser enviada ao usuário.

    Args:
        data: A lista de dados retornada pela API do WMS.
        item_code: O código do item consultado.

    Returns:
        A mensagem de texto formatada.
    """
    if not isinstance(data, list) or not data:
        return f"❌ Nenhum saldo encontrado para o item *{item_code}*.\nVerifique o código e tente novamente."

    reply_lines = [f"📦 Saldo para o item *{item_code}* (top 5):"]
    for i, item in enumerate(data[:5], start=1):
        qty = item.get("curr_qty", "0")
        loc = item.get("location_id__locn_str", "N/A")
        container = item.get("container_id__container_nbr", "N/A")
        status = item.get("container_id__status_id__description", "N/A")
        reply_lines.append(f"*{i}.* Qtd: *{qty}* | Local: {loc} | Cont.: {container} ({status})")
    
    reply_lines.append("\n_Para nova consulta, envie: *saldo [código]*_")
    return "\n".join(reply_lines)

async def send_whatsapp_message(phone: str, message: str):
    """
    Envia uma mensagem de resposta para o usuário via Z-API.

    Args:
        phone: O número de telefone do destinatário.
        message: A mensagem a ser enviada.
    """
    payload = {"phone": phone, "message": message}
    logger.info(f"Enviando resposta para {phone} via Z-API.")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.zapi_url, json=payload, timeout=10.0)
            response.raise_for_status()
            logger.info(f"Resposta enviada com sucesso para {phone}. Status: {response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Erro de rede ao enviar mensagem para a Z-API: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Erro de status HTTP da Z-API: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"Erro inesperado ao enviar mensagem para a Z-API: {e}")


# ========================
# ENDPOINT PRINCIPAL
# ========================

@app.post("/webhook", status_code=200)
async def receive_message(request: Request):
    """
    Endpoint que recebe as mensagens do WhatsApp. Trata a mensagem,
    consulta o WMS e envia a resposta.
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning("Payload recebido não é um JSON válido.")
        return {"status": "invalid_payload"}

    logger.info(f"Payload recebido: {body}")

    # Ignora mensagens enviadas pela própria API para evitar loops
    if body.get("fromMe") or body.get("fromApi", False):
        logger.info("Mensagem ignorada (originada pela API ou por mim).")
        return {"status": "ignored_from_api"}

    message_text = body.get("text", {}).get("message", "").lower().strip()
    phone = body.get("phone")

    if not message_text or not phone:
        logger.warning("Mensagem ou telefone não encontrados no payload.")
        return {"status": "ignored_missing_data"}

    logger.info(f"Mensagem recebida de {phone}: '{message_text}'")

    if "saldo" in message_text:
        parts = message_text.split("saldo", 1)
        item_code = parts[1].strip() if len(parts) > 1 else ""

        if not item_code:
            reply = "🤔 Para consultar o saldo, por favor, envie a mensagem no formato: *saldo [código do item]*"
            await send_whatsapp_message(phone, reply)
            return {"status": "processed_instruction_sent"}
            
        logger.info(f"Iniciando consulta de saldo para o item '{item_code}' para o telefone {phone}.")
        
        # 1. Consultar o WMS
        stock_data = await query_wms_for_stock(item_code)
        
        # 2. Formatar a resposta
        if stock_data is not None:
            reply_message = format_stock_reply(stock_data, item_code)
        else:
            reply_message = f"🚨 Ocorreu um erro ao consultar o sistema para o item *{item_code}*. Por favor, tente novamente mais tarde."
        
        # 3. Enviar a resposta via WhatsApp
        await send_whatsapp_message(phone, reply_message)
        
        return {"status": "processed_with_reply"}

    # Se a mensagem não contiver "saldo", podemos enviar uma ajuda ou ignorar
    logger.info(f"Comando não reconhecido na mensagem de {phone}.")
    # Descomente a linha abaixo para enviar uma mensagem de ajuda padrão
    # await send_whatsapp_message(phone, "Olá! Para consultar o saldo, envie: saldo [código do item]")
    return {"status": "ignored_command_not_found"}
