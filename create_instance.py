#!/usr/bin/env python3
import oci
import os
import requests
import logging
import time
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def send_telegram_msg(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            requests.get(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={text}", timeout=10)
        except Exception:
            pass

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

def main():
    logger.info("🚀 Запуск серии попыток создания сервера")

    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION"),
    }
    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    if not all(config.values()):
        logger.error("❌ Отсутствуют переменные OCI!")
        return

    compute_client = oci.core.ComputeClient(config)
    identity_client = oci.identity.IdentityClient(config)

    image_id = get_latest_image_id(compute_client, compartment_id)
    ads = identity_client.list_availability_domains(compartment_id=compartment_id).data
    
    if not image_id or not ads:
        logger.error("❌ Не удалось получить ID образа или AD")
        return

    # Цикл на 4 попытки
    for i in range(1, 5):
        logger.info(f"🔍 Попытка {i} из 4...")
        
        try:
            launch_details = oci.core.models.LaunchInstanceDetails(
                compartment_id=compartment_id,
                availability_domain=ads[0].name,
                display_name="always-free-arm",
                shape="VM.Standard.A1.Flex",
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=4, memory_in_gbs=24),
                source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image_id),
                create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet_id, assign_public_ip=True)
            )
            
            compute_client.launch_instance(launch_details)
            send_telegram_msg(f"✅ УРА! Сервер создан на {i}-й попытке!")
            return # Успех, выходим

        except oci.exceptions.ServiceError as e:
            if "out of capacity" in str(e).lower():
                logger.info(f"🔍 Нет ресурсов (попытка {i})")
                if i < 4:
                    time.sleep(600) # Пауза 10 минут перед следующей попыткой
                else:
                    send_telegram_msg("🔍 Все 4 попытки исчерпаны, ресурсов нет.")
            else:
                send_telegram_msg(f"⚠️ Ошибка: {str(e)[:50]}")
                break
        except Exception as e:
            send_telegram_msg(f"🚨 Ошибка: {str(e)[:50]}")
            break

if __name__ == "__main__":
    main()

