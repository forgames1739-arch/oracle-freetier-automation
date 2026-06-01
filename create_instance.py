#!/usr/bin/env python3
"""
Oracle Cloud Always Free ARM Ampere (4 ocpus / 24 GB)
Рандомный интервал 5–10 минут — чтобы выглядело как человек
"""

import oci
import os
import logging
import time
import random
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
        try:
            requests.get(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={text}", timeout=10)
        except Exception:
            pass

try:
    import requests
except ImportError:
    send_telegram_msg = lambda x: None

def main():
    logger.info("🚀 Запуск Always Free ARM Ampere с рандомными интервалами...")

    # === Настройки (обязательно заполни в env или GitHub Secrets) ===
    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    if not compartment_id:
        logger.error("❌ OCI_COMPARTMENT_OCID не найден")
        return

    subnet_id = os.getenv("OCI_SUBNET_OCID")
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

    compute_client = oci.core.ComputeClient(config)
    identity_client = oci.identity.IdentityClient(config)

    # === Получаем самый свежий образ Oracle Linux 9 ===
    image_id = get_latest_image_id(compute_client, compartment_id)
    if not image_id:
        logger.error("❌ Не удалось получить ID образа")
        return

    # === Availability Domain ===
    ads = identity_client.list_availability_domains(compartment_id=compartment_id).data
    if not ads:
        logger.error("❌ Нет Availability Domains")
        return
    ad_name = ads[0].name

    # === Shape config (ИСПРАВЛЕНО — только ocpus) ===
    shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=4,
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

    attempt = 0
    while True:
        attempt += 1
        wait_minutes = random.randint(5, 10)

        logger.info(f"\n🔄 Попытка №{attempt} — {datetime.now()}")
        logger.info(f"⏳ Следующая охота через {wait_minutes} минут...")

        send_telegram_msg(f"🔍 Новая охота в Always Free ARM Ampere через {wait_minutes} минут...")

        time.sleep(wait_minutes * 60)

        try:
            response = compute_client.launch_instance(launch_details)
            logger.info("="*70)
            logger.info(f"🎉 УРААА! Сервер создан! ID: {response.data.id}")
            logger.info("="*70)
            send_telegram_msg("✅ УРА! Always Free сервер создан!")
            return  # после успеха — выходим, чтобы не спамить

        except oci.exceptions.ServiceError as e:
            if "out of capacity" in str(e).lower() or "capacity" in str(e).lower():
                logger.warning("⚠️ Ресурсы заняты. Продолжаем охоту...")
                send_telegram_msg("🔍 Ресурсы заняты. Охота продолжается...")
            else:
                logger.error(f"❌ Ошибка: {str(e)[:150]}")
                send_telegram_msg(f"⚠️ Ошибка: {str(e)[:100]}")

        except Exception as e:
            logger.error(f"🚨 Неожиданная ошибка: {e}")
            send_telegram_msg(f"🚨 КРИТИКА: {str(e)[:100]}")

        logger.info("⏳ Ждём полную минуту перед следующей проверкой...")
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
    except Exception as e:
        logger.error(f"Ошибка получения образа: {e}")
    return None

if __name__ == "__main__":
    main()
