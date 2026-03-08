import requests
import os
import time
import logging
import traceback

# --- Environment Variables ---
CF_API_TOKEN = os.getenv("CF_API_TOKEN")
ZONE_NAME = os.getenv("CF_ZONE")
RECORD_NAMES = os.getenv("CF_RECORD", "").split(",")
RECORD_TYPE = os.getenv("CF_RECORD_TYPE", "A")  # A or AAAA
CF_PROXIED = os.getenv("CF_PROXIED", "false").lower() == "true"
INTERVAL = int(os.getenv("INTERVAL", "300"))  # seconds
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Logging Setup ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s"
)

HEADERS = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json",
}


def get_public_ip():
    url = "https://api.ipify.org" if RECORD_TYPE == "A" else "https://api6.ipify.org"
    ip = requests.get(url).text.strip()
    logging.debug(f"Public IP ({RECORD_TYPE}): {ip}")
    return ip


def get_zone_id():
    url = f"https://api.cloudflare.com/client/v4/zones?name={ZONE_NAME}"
    response = requests.get(url, headers=HEADERS).json()
    logging.debug(response)
    if not response["success"] or not response["result"]:
        raise Exception(f"Failed to get zone ID for {ZONE_NAME}")
    return response["result"][0]["id"]


def get_record(zone_id, record_name):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type={RECORD_TYPE}&name={record_name}"
    response = requests.get(url, headers=HEADERS).json()
    logging.debug(response)
    records = response.get("result", [])

    if not records:
        logging.warning(f"DNS record '{record_name}' not found. Skipping.")
        return None
    return records[0]


def update_record(zone_id, record_id, record_name, ip):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    data = {
        "type": RECORD_TYPE,
        "name": record_name,
        "content": ip,
        "ttl": 1,
        "proxied": CF_PROXIED,
    }
    response = requests.put(url, headers=HEADERS, json=data)
    if response.ok:
        logging.info(f"✔️ Updated {record_name} to {ip}")
    else:
        logging.error(f"❌ Failed to update {record_name}: {response.text}")


def main():
    while True:
        try:
            ip = get_public_ip()
            zone_id = get_zone_id()

            for record_name in RECORD_NAMES:
                record_name = record_name.strip()
                if not record_name:
                    continue

                record = get_record(zone_id, record_name)
                if record is None:
                    continue  # Skip if not found

                current_ip = record["content"]
                if current_ip != ip:
                    logging.info(f"IP change detected for {record_name}: {current_ip} -> {ip}")
                    update_record(zone_id, record["id"], record_name, ip)
                else:
                    logging.info(f"No change for {record_name}, still {ip}")

        except Exception as e:
            logging.error("Exception occurred:")
            logging.error(traceback.format_exc())

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
