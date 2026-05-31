import oci
import os
import requests

def send_telegram_msg(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={text}"
        try:
            requests.get(url)
        except Exception as e:
            print(f"Ошибка при отправке в Telegram: {e}")

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

    print("Попытка создания инстанса...")
    
    try:
        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=compartment_id,
            display_name="always-free-instance",
            shape="VM.Standard.A1.Flex",
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=4,
                memory_in_gbs=24
            ),
            source_details=oci.core.models.InstanceSourceViaImageDetails(
                image_id="ocid1.image.oc1.eu-zurich-1.aaaaaaaaxxxxxxxx" # ЗАМЕНИ НА СВОЙ ID ОБРАЗА
            ),
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=subnet_id
            )
        )
        
        compute_client.launch_instance(launch_details)
        msg = "УРА! Сервер в Oracle создан!"
        print(msg)
        send_telegram_msg(msg)
        
    except Exception as e:
        error_msg = f"Охота продолжается... Ошибка: {str(e)[:100]}"
        print(error_msg)
        # Отправлять сообщение каждые 10 минут при ошибке - плохая идея (заспамит)
        # Поэтому отправляем только если сервер НЕ создался, но логично это делать редко.

if __name__ == "__main__":
    create_instance()
