import os
import requests
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

# 🔹 Lendo variáveis de ambiente
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_CLIENT_TOKEN}/send-text"

ORACLE_AUTH = os.getenv("ORACLE_AUTH")
ORACLE_URL = "https://ta3.wms.ocs.oraclecloud.com/tpicomp_test/wms/lgfapi/v10/entity/inventory"

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    # Apenas processa mensagens recebidas
    if "text" in data.get("message", {}):
        mensagem = data["message"]["text"].get("message", "").strip().lower()
        numero = data["message"]["fromMe"] == False and data["message"]["phone"]

        if mensagem and numero:
            if "consultar ambiente tpi" in mensagem:
                resposta = consultar_oracle()
            else:
                resposta = "Comando não reconhecido."

            enviar_mensagem(numero, resposta)

    return {"status": "ok"}


def consultar_oracle():
    """Consulta dados no Oracle WMS Cloud"""
    try:
        params = {
            "container_id__status_id__description": "Located",
            "values_list": "id,item_id__code,location_id__locn_str,curr_qty",
            "item_id__code": "TESTRM"
        }
        headers = {
            "Authorization": ORACLE_AUTH
        }
        r = requests.get(ORACLE_URL, headers=headers, params=params)
        if r.status_code == 200:
            dados = r.json()
            return f"Consulta OK: {len(dados.get('items', []))} registros encontrados."
        else:
            return f"Erro Oracle ({r.status_code}): {r.text}"
    except Exception as e:
        return f"Erro na consulta Oracle: {str(e)}"


def enviar_mensagem(numero, mensagem):
    """Envia mensagem via Z-API"""
    payload = {
        "phone": numero,
        "message": mensagem
    }
    headers = {
        "Content-Type": "application/json"
    }
    r = requests.post(ZAPI_URL, json=payload, headers=headers)
    if r.status_code != 200:
        print(f"Erro ao enviar mensagem: {r.text}")
    return r.json()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
