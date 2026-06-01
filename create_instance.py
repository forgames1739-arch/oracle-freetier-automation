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
        send_telegram_msg(f"❌ ОШИБКА: Не удалось получить ID образа. {str(e)[:50]}")
    return None

def create_instance():
    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION")
    }

    try:
        # Инициализируем клиентов
        compute_client = oci.core.ComputeClient(config)
        identity_client = oci.identity.IdentityClient(config)  # IdentityClient (не ComputeClient!)

        compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
        subnet_id = os.getenv("OCI_SUBNET_OCID")
        
        image_id = get_latest_image_id(compute_client, compartment_id)
        if not image_id:
            return

        # Получаем Availability Domain из IdentityClient (правильно!)
        ads = identity_client.list_availability_domains(compartment_id=compartment_id).data
        if not ads:
            send_telegram_msg("❌ ОШИБКА: Нет доступных Availability Domains")
            return
        ad_name = ads[0].name

        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=compartment_id,
            availability_domain=ad_name,
            display_name="always-free-arm",
            shape="VM.Standard.A1.Flex",
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=4, memory_in_gbs=24),
            source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image_id),
            create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet_id, assign_public_ip=True)
        )
        
        compute_client.launch_instance(launch_details)
        send_telegram_msg("✅ УРА! Сервер успешно создан!")
        
    except oci.exceptions.ServiceError as e:
        if "Out of capacity" in str(e):
            send_telegram_msg("🔍 Охота продолжается: пока нет ресурсов.")
        else:
            send_telegram_msg(f"⚠️ ОШИБКА: {str(e)[:100]}")
    except Exception as e:
        send_telegram_msg(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {str(e)[:100]}")

if __name__ == "__main__":
    create_instance()
