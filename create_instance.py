#!/usr/bin/env python3
"""
Oracle Cloud Always Free ARM Ampere (4 ocpus / 24 GB)
Рандомный интервал 5–10 минут — работает ВЕЧНО
"""

import oci
import os
import requests
import logging
import time
import random
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler("oracle.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
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

def main():
    logger.info("🚀 Запуск Always Free ARM Ampere — ВЕЧНЫЙ РЕЖИМ")

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

    while True:
        # --- ВСТАВКА ЛОГИКИ ОЧЕРЕДИ ИЗ 3 ПОПЫТОК ---
        success = False
        for i in range(3):
            try:
                response = compute_client.launch_instance(launch_details)
                logger.info("🎉 УРААА! Always Free сервер создан!")
                logger.info(f"ID: {response.data.id}")
                send_telegram_msg("✅ УРА! Always Free сервер создан!")
                return # Успех, выходим полностью

            except oci.exceptions.ServiceError as e:
                if "out of capacity" in str(e).lower() or "capacity" in str(e).lower():
                    logger.info(f"🔍 Попытка {i+1}: Ресурсы заняты. Пробуем еще через 5 сек...")
                    time.sleep(20)
                else:
                    logger.error(f"❌ Ошибка: {str(e)[:150]}")
                    send_telegram_msg(f"⚠️ Ошибка: {str(e)[:100]}")
                    break 
            except Exception as e:
                logger.error(f"🚨 Неожиданная ошибка: {e}")
                send_telegram_msg(f"🚨 КРИТИКА: {str(e)[:100]}")
                break
        
        # Если после 3 попыток не вышло, уходим в обычный рандомный сон
        wait_minutes = random.randint(5, 10)
        logger.info(f"🔍 Очередь из 3 попыток исчерпана. Ждем {wait_minutes} минут...")
        time.sleep(wait_minutes * 60)

def get_latest_image_id(compute_client, compartment_id):
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            shape="VM.Standard.A1.Flex",
            operating_system="Oracle Linux",
            operating_system_version="9"
        ).data
        return images[0].id if images else None
    except Exception as e:
        logger.error(f"Ошибка получения образа: {e}")
    return None

if __name__ == "__main__":
    main()
