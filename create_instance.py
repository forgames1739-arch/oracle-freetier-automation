import oci
import os
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_telegram_msg(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={text}"
        try:
            requests.get(url)
        except Exception as e:
            logger.error(f"Ошибка при отправке в Telegram: {e}")

def get_latest_image_id(compute_client, compartment_id):
    """Автоматический поиск ID образа Oracle Linux 9 для ARM"""
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            shape="VM.Standard.A1.Flex",
            operating_system="Oracle Linux",
            operating_system_version="9"
        ).data
        if images:
            # Берем самый новый образ
            return images[0].id
    except Exception as e:
        logger.error(f"Ошибка поиска образа: {e}")
    return None

def create_instance():
    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION")
    }

    compute_client = oci.core.ComputeClient(config)
    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    image_id = get_latest_image_id(compute_client, compartment_id)
    if not image_id:
        logger.error("Не удалось определить ID образа автоматически!")
        return

    try:
        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=compartment_id,
            display_name="always-free-arm",
            shape="VM.Standard.A1.Flex",
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=4,
                memory_in_gbs=24
            ),
            source_details=oci.core.models.InstanceSourceViaImageDetails(
                image_id=image_id
            ),
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=subnet_id,
                assign_public_ip=True
            )
        )
        
        compute_client.launch_instance(launch_details)
        msg = "УРА! Сервер в Oracle создан!"
        logger.info(msg)
        send_telegram_msg(msg)
        
    except Exception as e:
        logger.warning(f"Ошибка при создании: {str(e)[:100]}")

if __name__ == "__main__":
    create_instance()
