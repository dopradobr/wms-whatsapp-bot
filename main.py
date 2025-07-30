from fastapi import FastAPI, Request
import httpx
import os
import logging

# ===========================================
# 🚀 Initialize FastAPI app and Logger
# ===========================================
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ===========================================
# 🔐 Environment Variables (Render)
# ===========================================
ORACLE_API_URL = os.getenv("ORACLE_API_URL")  # Base URL for Oracle WMS API
ORACLE_AUTH = os.getenv("ORACLE_AUTH")        # Oracle WMS API Authorization Token

ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

# Base URL for sending messages via Z-API
ZAPI_BASE_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

# ===========================================
# 📤 Send WhatsApp message via Z-API
# ===========================================
async def send_message(phone: str, message: str):
    url = f"{ZAPI_BASE_URL}/send-text"
    headers = {
        "Content-Type": "application/json",
        "client-token": ZAPI_CLIENT_TOKEN
    }
    payload = {
        "phone": phone,
        "message": message
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, headers=headers, json=payload)
        logging.info(f"📨 Z-API Response: {response.status_code} - {response.text}")

# ===========================================
# 📦 1 - Query LPNS in Receiving
# ===========================================
async def query_lpn_receiving():
    url = f"{ORACLE_API_URL}&container_id__status_id__description=Received"
    headers = {"Authorization": ORACLE_AUTH}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
        data = r.json()

    results = data.get("results", [])
    if not results:
        return "📦 No LPNs in Receiving."

    response = ["📦 *LPNs in Receiving:*"]
    for rec in results:
        response.append(f"• LPN: `{rec.get('container_id__container_nbr')}` | Qty: *{rec.get('curr_qty')}* | Item: {rec.get('item_id__code')}")
    return "\n".join(response)

# ===========================================
# 📦 2 - Query Stored Items (Ordered by Location)
# ===========================================
async def query_stored_items():
    url = f"{ORACLE_API_URL}&container_id__status_id__description=Located"
    headers = {"Authorization": ORACLE_AUTH}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
        data = r.json()

    results = data.get("results", [])
    if not results:
        return "📦 No stored items found."

    # Sort by location
    results_sorted = sorted(results, key=lambda x: x.get("container_id__curr_location_id__locn_str", ""))

    response = ["📦 *Stored Items:*"]
    for rec in results_sorted:
        response.append(f"• Item: `{rec.get('item_id__code')}` | Qty: *{rec.get('curr_qty')}* | 📍 {rec.get('container_id__curr_location_id__locn_str')}")
    return "\n".join(response)

# ===========================================
# 📦 3 - Query Item Balance (Located sorted by Location)
# ===========================================
async def query_item_balance(item: str):
    url = f"{ORACLE_API_URL}&item_id__code={item}"
    headers = {"Authorization": ORACLE_AUTH}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            data = response.json()

        records = data.get("results", [])
        if not records:
            return f"❌ No balance found for item {item}."

        located = []
        received = []

        for r in records:
            status = r.get("container_id__status_id__description", "").lower()
            info = {
                "lpn": r.get("container_id__container_nbr", "-"),
                "qty": int(float(r.get("curr_qty", 0))),
                "location": r.get("container_id__curr_location_id__locn_str") or "-"
            }
            if status == "located":
                located.append(info)
            else:
                received.append(info)

        # Sort Located by location
        located = sorted(located, key=lambda x: x["location"])

        total_located = sum([i["qty"] for i in located])
        total_received = sum([i["qty"] for i in received])

        response = [f"📦 *Item Balance:* `{item}`", ""]

        if located:
            response.append("🔹 *Located (Ready to Use)*")
            for i in located:
                response.append(f"• LPN: `{i['lpn']}` | Qty: *{i['qty']}* | 📍 {i['location']}")
            response.append("")

        if received:
            response.append("🔸 *Received (Pending Storage)*")
            for i in received:
                response.append(f"• LPN: `{i['lpn']}` | Qty: *{i['qty']}*")
            response.append("")

        response.append(f"📊 Total Located: *{total_located}*")
        response.append(f"📊 Total Received: *{total_received}*")

        return "\n".join(response)

    except Exception as e:
        return f"❌ Error checking item balance: {str(e)}"

# ===========================================
# 📦 4 - Query Items by Specific Location
# ===========================================
async def query_items_by_location(location: str):
    url = f"{ORACLE_API_URL}&location_id__locn_str={location}"
    headers = {"Authorization": ORACLE_AUTH}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
        data = r.json()

    results = data.get("results", [])
    if not results:
        return f"📍 No items found at location {location}."

    response = [f"📍 *Items at Location:* `{location}`"]
    for rec in results:
        response.append(f"• Item: `{rec.get('item_id__code')}` | LPN: `{rec.get('container_id__container_nbr')}` | Qty: *{rec.get('curr_qty')}*")
    return "\n".join(response)

# ===========================================
# 📥 Webhook - Receives WhatsApp Messages
# ===========================================
@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    logging.info(f"📥 Incoming payload: {payload}")

    try:
        phone = payload.get("phone")
        text = payload.get("text", {}).get("message", "").strip().lower()

        # 🔍 Supported Commands
        if text.startswith("balance wms "):
            item = text.split("balance wms ", 1)[1].strip().upper()
            response = await query_item_balance(item)

        elif text == "lpn receiving":
            response = await query_lpn_receiving()

        elif text == "stored items":
            response = await query_stored_items()

        elif text.startswith("location "):
            location = text.split("location ", 1)[1].strip().upper()
            response = await query_items_by_location(location)

        else:
            response = (
                "❌ Command not recognized.\n\n"
                "📌 Available Commands:\n"
                "• balance wms ITEM123\n"
                "• lpn receiving\n"
                "• stored items\n"
                "• location A01-01-01"
            )

        await send_message(phone, response)

    except Exception as e:
        logging.error(f"❌ Webhook error: {str(e)}")

    return {"status": "ok"}
