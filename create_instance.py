#!/usr/bin/env python3
"""
Oracle Always Free ARM Hunter v2.0
Создаёт VM.Standard.A1.Flex (4 OCPU, 24GB) + уведомления в Telegram
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

MIN_WAIT = 90
MAX_WAIT = 240
MAX_ATTEMPTS = 0          # 0 = бесконечно
BACKOFF_FACTOR = 1.5

# =========================
# TELEGRAM
# =========================

def send_telegram_msg(text: str, parse_mode: str = "HTML"):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            },
            timeout=10
        )
        return True
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение в Telegram: {e}")
        return False


# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("oracle_hunter.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def tg_log(text: str, level: str = "INFO"):
    """Логирование + Telegram"""
    if level == "ERROR":
        logger.error(text)
        send_telegram_msg(f"❌ <b>Error</b>\n{text}")
    elif level == "WARNING":
        logger.warning(text)
        send_telegram_msg(f"⚠️ <b>Warning</b>\n{text}")
    else:
        logger.info(text)
        send_telegram_msg(f"ℹ️ {text}")


# =========================
# OCI HELPERS
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
    """Проверяем наличие активного/создаваемого ARM инстанса"""
    try:
        instances = compute_client.list_instances(
            compartment_id=compartment_id,
            lifecycle_state=["PROVISIONING", "STARTING", "RUNNING", "STOPPING", "STOPPED"]
        ).data

        for inst in instances:
            if inst.shape == "VM.Standard.A1.Flex":
                tg_log(f"✅ Уже существует инстанс: {inst.display_name} ({inst.id})", "WARNING")
                return True
        return False
    except Exception as e:
        tg_log(f"Ошибка проверки существующих инстансов: {e}", "ERROR")
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
        tg_log(f"Не удалось получить список образов: {e}", "ERROR")
        return None


# =========================
# MAIN
# =========================

def signal_handler(sig, frame):
    tg_log("🛑 Скрипт остановлен пользователем (Ctrl+C)")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)

    tg_log("🚀 <b>Oracle Always Free ARM Hunter v2.0</b> запущен")

    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    if not compartment_id:
        tg_log("❌ OCI_COMPARTMENT_OCID не указан", "ERROR")
        return
    if not subnet_id:
        tg_log("❌ OCI_SUBNET_OCID не указан", "ERROR")
        return

    try:
        config = get_oci_config()
        compute_client = oci.core.ComputeClient(config)
        identity_client = oci.identity.IdentityClient(config)

        # Увеличиваем таймауты
        for client in (compute_client, identity_client):
            client.base_client.timeout = (15, 60)
    except Exception as e:
        tg_log(f"Ошибка инициализации OCI: {e}", "ERROR")
        return

    if instance_exists(compute_client, compartment_id):
        return

    image_id = get_latest_image_id(compute_client, compartment_id)
    if not image_id:
        tg_log("❌ Не найден образ Oracle Linux 9 для A1.Flex", "ERROR")
        return

    # Availability Domain
    try:
        ads = identity_client.list_availability_domains(compartment_id=compartment_id).data
        ad_name = ads[0].name
        tg_log(f"📍 Используем Availability Domain: <code>{ad_name}</code>")
    except Exception as e:
        tg_log(f"Ошибка получения AD: {e}", "ERROR")
        return

    # Launch details
    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=compartment_id,
        display_name="always-free-arm-4c24g",
        image_id=image_id,
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=4,
            memory_in_gbs=24
        ),
        availability_domain=ad_name,
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True
        ),
        # Можно добавить cloud-init
        # metadata={"user_data": base64.b64encode(your_script.encode()).decode()}
    )

    attempt = 0

    while MAX_ATTEMPTS == 0 or attempt < MAX_ATTEMPTS:
        attempt += 1
        wait_time = random.randint(MIN_WAIT, MAX_WAIT)

        try:
            tg_log(f"🔄 Попытка #{attempt} | Ожидание перед попыткой: {wait_time}с")
            time.sleep(wait_time)

            response = compute_client.launch_instance(launch_details)
            instance = response.data

            tg_log(
                f"🎉 <b>ИНСТАНС УСПЕШНО СОЗДАН!</b>\n\n"
                f"<b>ID:</b> <code>{instance.id}</code>\n"
                f"<b>AD:</b> {instance.availability_domain}\n"
                f"<b>OCPU:</b> 4 | <b>RAM:</b> 24GB",
                "INFO"
            )
            return

        except oci.exceptions.ServiceError as e:
            if e.status == 429:
                tg_log("⏳ 429 Too Many Requests. Ждём 5 минут...", "WARNING")
                time.sleep(300)
                continue

            error_msg = str(e).lower()
            if any(x in error_msg for x in ["capacity", "out of host capacity", "limit exceeded"]):
                tg_log(f"🌍 Нет свободной ёмкости в AD. Ждём {wait_time}с...", "WARNING")
                continue

            tg_log(
                f"❌ OCI Service Error\n"
                f"Status: {e.status}\n"
                f"Code: {e.code}\n"
                f"Message: {e.message}",
                "ERROR"
            )
            time.sleep(60)

        except Exception as e:
            tg_log(f"🚨 Неожиданная ошибка: {e}", "ERROR")
            time.sleep(60)

    tg_log("⛔ Достигнуто максимальное количество попыток", "ERROR")


if __name__ == "__main__":
    main()
