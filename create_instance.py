#!/usr/bin/env python3
"""
Oracle Always Free ARM Hunter v2.1
Автоматическое создание VM.Standard.A1.Flex (4 OCPU, 24GB)
с уведомлениями в Telegram
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
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            },
            timeout=10
        )
        return True
    except Exception as e:
        logging.error(f"Telegram send error: {e}")
        return False


# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler("oracle_hunter.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def tg_log(text: str, level: str = "INFO"):
    """Логирование + отправка в Telegram"""
    emoji = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "SUCCESS": "🎉"
    }.get(level, "➤")

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
        raise RuntimeError(f"Отсутствуют OCI переменные окружения: {', '.join(missing)}")

    return config


def instance_exists(compute_client, compartment_id: str) -> bool:
    """Проверяем наличие уже существующего/создаваемого A1.Flex инстанса"""
    try:
        instances = compute_client.list_instances(
            compartment_id=compartment_id
        ).data

        active_states = {
            "PROVISIONING", "STARTING", "RUNNING",
            "STOPPING", "STOPPED", "CREATING_IMAGE"
        }

        for inst in instances:
            if inst.shape == "VM.Standard.A1.Flex" and inst.lifecycle_state in active_states:
                tg_log(
                    f"✅ Уже существует инстанс:\n"
                    f"• Имя: <code>{inst.display_name}</code>\n"
                    f"• ID: <code>{inst.id}</code>\n"
                    f"• Статус: {inst.lifecycle_state}",
                    "WARNING"
                )
                return True
        return False

    except Exception as e:
        tg_log(f"Ошибка при проверке существующих инстансов: {e}", "ERROR")
        return False


def get_latest_image_id(compute_client, compartment_id: str) -> Optional[str]:
    """Получаем самый свежий образ Oracle Linux 9"""
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
        tg_log(f"🖼️ Найден образ: {latest.display_name}")
        return latest.id

    except Exception as e:
        tg_log(f"Ошибка получения списка образов: {e}", "ERROR")
        return None


# =========================
# MAIN
# =========================

def signal_handler(sig, frame):
    tg_log("🛑 Скрипт остановлен пользователем (Ctrl+C)", "WARNING")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tg_log("<b>🚀 Oracle Always Free ARM Hunter v2.1</b> запущен", "INFO")

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
        tg_log(f"Ошибка инициализации OCI клиента: {e}", "ERROR")
        return

    # Проверка существующих инстансов
    if instance_exists(compute_client, compartment_id):
        return

    # Получаем образ
    image_id = get_latest_image_id(compute_client, compartment_id)
    if not image_id:
        tg_log("❌ Не удалось найти подходящий образ Oracle Linux 9", "ERROR")
        return

    # Availability Domain
    try:
        ads = identity_client.list_availability_domains(
            compartment_id=compartment_id
        ).data
        if not ads:
            tg_log("❌ Availability Domains не найдены", "ERROR")
            return
        ad_name = ads[0].name
        tg_log(f"📍 Используем Availability Domain: <code>{ad_name}</code>")
    except Exception as e:
        tg_log(f"Ошибка получения Availability Domain: {e}", "ERROR")
        return

    # Конфигурация запуска
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
        # Здесь можно добавить cloud-init (пример ниже)
        # metadata={"user_data": "..."}
    )

    attempt = 0

    while MAX_ATTEMPTS == 0 or attempt < MAX_ATTEMPTS:
        attempt += 1
        wait_time = random.randint(MIN_WAIT, MAX_WAIT)

        try:
            tg_log(f"🔄 Попытка #{attempt} | Ожидание: {wait_time} сек.")
            time.sleep(wait_time)

            response = compute_client.launch_instance(launch_details)
            instance = response.data

            tg_log(
                f"<b>🎉 ИНСТАНС УСПЕШНО СОЗДАН!</b>\n\n"
                f"<b>ID:</b> <code>{instance.id}</code>\n"
                f"<b>AD:</b> {instance.availability_domain}\n"
                f"<b>Shape:</b> VM.Standard.A1.Flex (4 OCPU / 24 GB)",
                "SUCCESS"
            )
            return

        except oci.exceptions.ServiceError as e:
            if e.status == 429:
                tg_log("⏳ 429 Too Many Requests — ждём 5 минут...", "WARNING")
                time.sleep(300)
                continue

            error_lower = str(e).lower()
            if any(keyword in error_lower for keyword in ["capacity", "out of host capacity", "limit exceeded"]):
                tg_log(f"🌍 Нет свободной ёмкости. Ждём {wait_time} сек...", "WARNING")
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
