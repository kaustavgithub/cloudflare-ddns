import requests
import os
import time
import logging
import traceback

# --- Environment Variables ---
CF_API_TOKEN = os.getenv("CF_API_TOKEN")
ZONE_NAME = os.getenv("CF_ZONE")
RECORDS_FILE = os.getenv("CF_RECORDS_FILE", "/config/records.conf")
DEFAULT_RECORD_TYPE = os.getenv("CF_RECORD_TYPE", "A")  # A or AAAA
DEFAULT_PROXIED = os.getenv("CF_PROXIED", "false").lower() == "true"
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

IP_URLS = {"A": "https://api.ipify.org", "AAAA": "https://api6.ipify.org"}


def parse_records(text):
    """One record per line: `name [type=A] [proxied=true]`. '#' starts a comment."""
    records = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        name, *options = line.split()
        record_type = DEFAULT_RECORD_TYPE
        proxied = DEFAULT_PROXIED

        for option in options:
            key, _, value = option.partition("=")
            key = key.lower()
            if key == "type":
                record_type = value.upper()
            elif key == "proxied":
                proxied = value.lower() == "true"
            else:
                logging.warning(f"{RECORDS_FILE}:{lineno}: ignoring unknown option '{option}'")

        if record_type not in IP_URLS:
            logging.warning(f"{RECORDS_FILE}:{lineno}: unsupported type '{record_type}' for {name}. Skipping.")
            continue

        records.append((name, record_type, proxied))
    return records


def load_records():
    """Re-read the record list every cycle so edits apply without a restart."""
    try:
        with open(RECORDS_FILE) as f:
            return parse_records(f.read())
    except FileNotFoundError:
        logging.warning(f"{RECORDS_FILE} not found, falling back to the CF_RECORD env var")
        return parse_records("\n".join(os.getenv("CF_RECORD", "").split(",")))


def get_public_ip(record_type):
    ip = requests.get(IP_URLS[record_type]).text.strip()
    logging.debug(f"Public IP ({record_type}): {ip}")
    return ip


def get_zone_id():
    url = f"https://api.cloudflare.com/client/v4/zones?name={ZONE_NAME}"
    response = requests.get(url, headers=HEADERS).json()
    logging.debug(response)
    if not response["success"] or not response["result"]:
        raise Exception(f"Failed to get zone ID for {ZONE_NAME}")
    return response["result"][0]["id"]


def get_record(zone_id, record_name, record_type):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type={record_type}&name={record_name}"
    response = requests.get(url, headers=HEADERS).json()
    logging.debug(response)
    records = response.get("result", [])

    if not records:
        logging.warning(f"DNS record '{record_name}' not found. Skipping.")
        return None
    return records[0]


def update_record(zone_id, record_id, record_name, record_type, proxied, ip):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    data = {
        "type": record_type,
        "name": record_name,
        "content": ip,
        "ttl": 1,
        "proxied": proxied,
    }
    response = requests.put(url, headers=HEADERS, json=data)
    if response.ok:
        logging.info(f"✔️ Updated {record_name} to {ip}")
    else:
        logging.error(f"❌ Failed to update {record_name}: {response.text}")


def main():
    previous_records = None

    while True:
        try:
            records = load_records()
            if records != previous_records:
                names = ", ".join(name for name, _, _ in records) or "(none)"
                logging.info(f"Loaded {len(records)} record(s) from config: {names}")
                previous_records = records

            if records:
                zone_id = get_zone_id()
                ips = {}

                for record_name, record_type, proxied in records:
                    if record_type not in ips:
                        ips[record_type] = get_public_ip(record_type)
                    ip = ips[record_type]

                    record = get_record(zone_id, record_name, record_type)
                    if record is None:
                        continue  # Skip if not found

                    current_ip = record["content"]
                    if current_ip != ip:
                        logging.info(f"IP change detected for {record_name}: {current_ip} -> {ip}")
                        update_record(zone_id, record["id"], record_name, record_type, proxied, ip)
                    else:
                        logging.info(f"No change for {record_name}, still {ip}")

        except Exception as e:
            logging.error("Exception occurred:")
            logging.error(traceback.format_exc())

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
