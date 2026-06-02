#!/usr/bin/env python3

import oci
import os
import requests
import logging
import time
import random

# =========================
# НАСТРОЙКИ
# =========================

MIN_WAIT = 120
MAX_WAIT = 180

# =========================
# TELEGRAM
# =========================

def send_telegram_msg(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text
            },
            timeout=10
        )
    except Exception:
        pass


# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler("oracle.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def telegram_log(text):
    logger.info(text)
    send_telegram_msg(text)


# =========================
# OCI
# =========================

def get_config():
    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION"),
    }

    if not all(config.values()):
        raise RuntimeError("Не заполнены OCI переменные")

    return config


def get_latest_image_id(compute_client, compartment_id):
    images = compute_client.list_images(
        compartment_id=compartment_id,
        shape="VM.Standard.A1.Flex",
        operating_system="Oracle Linux",
        operating_system_version="9"
    ).data

    if not images:
        return None

    images.sort(
        key=lambda x: x.time_created,
        reverse=True
    )

    return images[0].id


def instance_exists(compute_client, compartment_id):
    instances = compute_client.list_instances(
        compartment_id=compartment_id
    ).data

    for instance in instances:
        if instance.lifecycle_state in (
            "PROVISIONING",
            "STARTING",
            "RUNNING",
            "STOPPING",
            "STOPPED"
        ):
            if instance.shape == "VM.Standard.A1.Flex":
                return True

    return False


# =========================
# MAIN
# =========================

def main():

    telegram_log("🚀 Oracle Always Free Hunter запущен")

    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    if not compartment_id:
        telegram_log("❌ OCI_COMPARTMENT_OCID отсутствует")
        return

    if not subnet_id:
        telegram_log("❌ OCI_SUBNET_OCID отсутствует")
        return

    config = get_config()

    compute_client = oci.core.ComputeClient(config)
    identity_client = oci.identity.IdentityClient(config)

    compute_client.base_client.timeout = (10, 30)
    identity_client.base_client.timeout = (10, 30)

    if instance_exists(compute_client, compartment_id):
        telegram_log("✅ ARM инстанс уже существует")
        return

    image_id = get_latest_image_id(
        compute_client,
        compartment_id
    )

    if not image_id:
        telegram_log("❌ Не удалось получить образ Oracle Linux 9")
        return

    ads = identity_client.list_availability_domains(
        compartment_id=compartment_id
    ).data

    if not ads:
        telegram_log("❌ Availability Domains не найдены")
        return

    ad_name = ads[0].name

    telegram_log(f"📦 Используем AD: {ad_name}")

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

        logger.info(f"Попытка #{attempt}")

        try:

            response = compute_client.launch_instance(
                launch_details
            )

            instance_id = response.data.id

            telegram_log(
                f"🎉 ИНСТАНС СОЗДАН!\n\nID:\n{instance_id}"
            )

            return

        except oci.exceptions.ServiceError as e:

            if e.status == 429:

                telegram_log(
                    "⚠️ Oracle вернул 429 Too Many Requests.\n"
                    "Ожидание 5 минут."
                )

                time.sleep(300)
                continue

            error_text = str(e).lower()

            if (
                "capacity" in error_text
                or "out of host capacity" in error_text
            ):

                wait_time = random.randint(
                    MIN_WAIT,
                    MAX_WAIT
                )

                logger.info(
                    f"Нет свободной ёмкости. "
                    f"Следующая попытка через "
                    f"{wait_time} сек."
                )

                time.sleep(wait_time)
                continue

            telegram_log(
                f"❌ OCI ERROR\n"
                f"Status: {e.status}\n"
                f"Code: {e.code}\n"
                f"Message: {e.message}"
            )

            time.sleep(300)

        except Exception as e:

            telegram_log(
                f"🚨 Неожиданная ошибка:\n{e}"
            )

            time.sleep(300)


if __name__ == "__main__":
    main()
