#!/usr/bin/env python3
"""
Oracle Always Free ARM Hunter v2.2 — оптимизирован для GitHub Actions
"""

import oci
import os
import requests
import logging
import time
import random
import sys
import signal
from typing import Optional

# =========================
# НАСТРОЙКИ
# =========================

MIN_WAIT = 120
MAX_WAIT = 240
RUN_FOR_HOURS = 5.5   # Работать чуть меньше 6 часов

# =========================
# TELEGRAM + LOGGING (без изменений, оставил как в v2.1)
# =========================

def send_telegram_msg(text: str, parse_mode: str = "HTML"):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True},
            timeout=10
        )
        return True
    except:
        return False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler("oracle_hunter.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def tg_log(text: str, level: str = "INFO"):
    emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "SUCCESS": "🎉"}.get(level, "➤")
    if level == "ERROR":
        logger.error(text)
        send_telegram_msg(f"{emoji} <b>Error</b>\n{text}")
    elif level == "WARNING":
        logger.warning(text)
        send_telegram_msg(f"{emoji} <b>Warning</b>\n{text}")
    elif level == "SUCCESS":
        logger.info(text)
        send_telegram_msg(f"{emoji} {text}")
    else:
        logger.info(text)
        send_telegram_msg(f"{emoji} {text}")

# =========================
# OCI функции (те же, что раньше)
# =========================

def get_oci_config() -> dict:
    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION"),
    }
    missing = [k for k, v in config.items() if not v]
    if missing:
        raise RuntimeError(f"Отсутствуют OCI переменные: {', '.join(missing)}")
    return config

def instance_exists(compute_client, compartment_id: str) -> bool:
    try:
        instances = compute_client.list_instances(compartment_id=compartment_id).data
        active_states = {"PROVISIONING", "STARTING", "RUNNING", "STOPPING", "STOPPED", "CREATING_IMAGE"}
        for inst in instances:
            if inst.shape == "VM.Standard.A1.Flex" and inst.lifecycle_state in active_states:
                tg_log(f"✅ Уже существует инстанс: {inst.display_name} ({inst.id})", "WARNING")
                return True
        return False
    except Exception as e:
        tg_log(f"Ошибка проверки инстансов: {e}", "ERROR")
        return False

def get_latest_image_id(compute_client, compartment_id: str) -> Optional[str]:
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            shape="VM.Standard.A1.Flex",
            operating_system="Oracle Linux",
            operating_system_version="9"
        ).data
        if not images:
            return None
        latest = max(images, key=lambda x: x.time_created)
        return latest.id
    except Exception as e:
        tg_log(f"Ошибка получения образа: {e}", "ERROR")
        return None

# =========================
# MAIN
# =========================

def main():
    start_time = time.time()
    tg_log("<b>🚀 Oracle Always Free ARM Hunter v2.2</b> запущен", "INFO")

    # ... (весь код инициализации OCI, проверки инстанса, образа, AD — как в предыдущей версии)

    # Вставь сюда весь основной код из v2.1 (get_oci_config, instance_exists, get_latest_image_id, launch_details)

    attempt = 0
    while True:
        if (time.time() - start_time) / 3600 > RUN_FOR_HOURS:
            tg_log("⏰ Достигнуто ограничение по времени (GitHub Actions). Останавливаемся.", "WARNING")
            break

        attempt += 1
        wait_time = random.randint(MIN_WAIT, MAX_WAIT)

        try:
            tg_log(f"🔄 Попытка #{attempt} | Ожидание: {wait_time} сек.")
            time.sleep(wait_time)

            # launch_instance код...

        except Exception as e:
            # обработка ошибок как раньше
            pass

if __name__ == "__main__":
    main()
