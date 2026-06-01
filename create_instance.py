#!/usr/bin/env python3
"""
Oracle Cloud Always Free ARM Ampere (4 vCPU, 24GB) — ИСПРАВЛЕНО 2026
"""

import oci
import os
import logging
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def send_telegram_msg(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={text}"
        try:
            requests.get(url, timeout=10)  # requests нужно установить
        except Exception as e:
            logger.error(f"Ошибка Telegram: {e}")

# === ИМПОРТ (для send_telegram_msg) ===
try:
    import requests
except ImportError:
    logger.warning("requests не установлен — Telegram отключён")
    send_telegram_msg = lambda x: None

def main():
    logger.info("🚀 Запуск Oracle Always Free ARM Ampere...")

    # === НАСТРОЙКИ ===
    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    if not compartment_id:
        logger.error("❌ OCI_COMPARTMENT_OCID не найден")
        return

    subnet_id = os.getenv("OCI_SUBNET_OCID")
    if not subnet_id:
        logger.error("❌ OCI_SUBNET_OCID не найден")
        return

    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION"),
    }

    if not all(config.values()):
        logger.error("❌ Отсутствуют переменные OCI!")
        return

    # Клиенты
    compute_client = oci.core.ComputeClient(config)
    identity_client = oci.identity.IdentityClient(config)

    image_id = get_latest_image_id(compute_client, compartment_id)
    if not image_id:
        logger.error("❌ Не удалось получить ID образа")
        return

    ads = identity_client.list_availability_domains(compartment_id=compartment_id).data
    if not ads:
        logger.error("❌ Нет Availability Domains")
        return
    ad_name = ads[0].name

    shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=4,                    # ИСПРАВЛЕНО! Только ocpus
        memory_in_gbs=24
    )

    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=compartment_id,
        display_name="always-free-arm",
        image_id=image_id,
        shape="VM.Standard.A1.Flex",
        shape_config=shape_config,
        availability_domain=ad_name,
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True
        )
    )

    # ====================== РЕТРАЙ (бесконечный) ======================
    attempt = 0
    while True:
        attempt += 1
        logger.info(f"\n🔄 Попытка №{attempt} — {datetime.now()}")

        try:
            response = compute_client.launch_instance(launch_details)
            instance_id = response.data.id
            logger.info("="*60)
            logger.info(f"🎉 СУПЕР! Сервер создан! ID: {instance_id}")
            logger.info("="*60)
            send_telegram_msg("✅ УРА! Always Free сервер создан!")
            return

        except oci.exceptions.ServiceError as e:
            if "out of capacity" in str(e).lower() or "capacity" in str(e).lower():
                logger.warning(f"⚠️ Ресурсы заняты (Out of capacity). Охота продолжается...")
                send_telegram_msg("🔍 Ресурсы заняты. Охота продолжается...")
            else:
                logger.error(f"❌ Сервисная ошибка: {str(e)[:150]}")
                send_telegram_msg(f"⚠️ Ошибка: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"🚨 Неожиданная ошибка: {e}")
            send_telegram_msg(f"🚨 КРИТИКА: {str(e)[:100]}")

        logger.info("⏳ Ждём 60 секунд...")
        time.sleep(60)

def get_latest_image_id(compute_client, compartment_id):
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            shape="VM.Standard.A1.Flex",
            operating_system="Oracle Linux",
            operating_system_version="9"
        ).data
        if images:
            return images[0].id
        logger.warning("Образ не найден")
    except Exception as e:
        logger.error(f"Ошибка получения образа: {e}")
    return None

if __name__ == "__main__":
    main()
