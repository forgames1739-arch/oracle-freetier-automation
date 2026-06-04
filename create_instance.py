#!/usr/bin/env python3
"""
Oracle Always Free ARM Hunter v2.9
Надёжный вечный режим + Telegram + автоперезапуск
"""

import oci
import os
import requests
import logging
import time
import random
import sys
from datetime import datetime

# =========================
# НАСТРОЙКИ
# =========================

MIN_WAIT = 120
MAX_WAIT = 150
RUN_FOR_HOURS = 4.8

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("oracle.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def send_telegram_msg(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass

def tg_log(text: str, level: str = "INFO"):
    emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "SUCCESS": "🎉"}.get(level, "")
    logger.info(text)
    send_telegram_msg(f"{emoji} {text}")


# =========================
# OCI FUNCTIONS
# =========================

def get_oci_config():
    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION"),
    }
    if not all(config.values()):
        raise RuntimeError("❌ Не все OCI переменные заполнены!")
    return config


def get_latest_image_id(compute_client, compartment_id):
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            shape="VM.Standard.A1.Flex",
            operating_system="Oracle Linux",
            operating_system_version="9"
        ).data
        if images:
            latest = max(images, key=lambda x: x.time_created)
            tg_log(f"🖼️ Используем образ: {latest.display_name}")
            return latest.id
        return None
    except Exception as e:
        tg_log(f"Ошибка получения образа: {e}", "ERROR")
        return None


def instance_exists(compute_client, compartment_id):
    try:
        instances = compute_client.list_instances(compartment_id=compartment_id).data
        for inst in instances:
            if inst.shape == "VM.Standard.A1.Flex" and inst.lifecycle_state not in ["TERMINATED", "TERMINATING"]:
                tg_log(f"✅ Инстанс уже существует: {inst.display_name} ({inst.lifecycle_state})", "WARNING")
                return True
        return False
    except Exception as e:
        tg_log(f"Ошибка проверки инстансов: {e}", "ERROR")
        return False


# =========================
# MAIN
# =========================

def main():
    start_time = time.time()
    tg_log("<b>🚀 Oracle Always Free ARM Hunter v2.9 запущен</b>")

    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    if not compartment_id or not subnet_id:
        tg_log("❌ Не указаны COMPARTMENT_OCID или SUBNET_OCID", "ERROR")
        return

    try:
        config = get_oci_config()
        compute_client = oci.core.ComputeClient(config)
        identity_client = oci.identity.IdentityClient(config)

        for client in (compute_client, identity_client):
            client.base_client.timeout = (15, 60)
    except Exception as e:
        tg_log(f"❌ Ошибка инициализации OCI: {e}", "ERROR")
        return

    if instance_exists(compute_client, compartment_id):
        return

    image_id = get_latest_image_id(compute_client, compartment_id)
    if not image_id:
        tg_log("❌ Не удалось получить образ", "ERROR")
        return

    try:
        ads = identity_client.list_availability_domains(compartment_id=compartment_id).data
        ad_name = ads[0].name
        tg_log(f"📍 AD: <code>{ad_name}</code>")
    except Exception as e:
        tg_log(f"Ошибка AD: {e}", "ERROR")
        return

    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=compartment_id,
        display_name="always-free-arm-4c24g",
        image_id=image_id,
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=4, memory_in_gbs=24),
        availability_domain=ad_name,
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True
        )
    )

    attempt = 0

    while True:
        # Проверка времени работы
        if (time.time() - start_time) / 3600 > RUN_FOR_HOURS:
            tg_log("⏰ Достигнуто время работы (\~5ч 51м). Останавливаемся до следующего запуска.", "WARNING")
            break

        attempt += 1
        wait_time = random.randint(MIN_WAIT, MAX_WAIT)

        try:
            tg_log(f"🔄 Попытка #{attempt} • Ожидание {wait_time} сек.")
            time.sleep(wait_time)

            response = compute_client.launch_instance(launch_details)
            instance = response.data

            tg_log(
                f"<b>🎉 ИНСТАНС УСПЕШНО СОЗДАН!</b>\n\n"
                f"ID: <code>{instance.id}</code>\n"
                f"AD: {instance.availability_domain}",
                "SUCCESS"
            )
            return

        except oci.exceptions.ServiceError as e:
            if e.status == 429:
                tg_log("⏳ 429 Too Many Requests — ждём 5 минут...", "WARNING")
                time.sleep(300)
                continue

            error_text = str(e).lower()
            if any(x in error_text for x in ["capacity", "out of host capacity", "not enough resources"]):
                tg_log(f"🌍 Нет свободных ресурсов. Ждём {wait_time} сек...", "WARNING")
            else:
                tg_log(f"❌ OCI Error: {e.status} | {e.code} | {e.message}", "ERROR")
                time.sleep(60)

        except Exception as e:
            tg_log(f"🚨 Неожиданная ошибка: {e}", "ERROR")
            time.sleep(60)


if __name__ == "__main__":
    main()
