import oci
import os
import sys

def create_instance():
    # Загрузка конфигурации из переменных окружения
    config = {
        "user": os.getenv("OCI_USER_OCID"),
        "key_content": os.getenv("OCI_PRIVATE_KEY"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "region": os.getenv("OCI_REGION")
    }

    # Инициализация клиента
    compute_client = oci.core.ComputeClient(config)
    
    # Параметры запроса
    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    print("Попытка создания инстанса...")

    # Пример запроса (базовая логика)
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
                image_id="ocid1.image.oc1.eu-zurich-1.aaaaaaaaxxxxxxxx" # Замени на нужный ID образа
            ),
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=subnet_id
            )
        )
        
        response = compute_client.launch_instance(launch_details)
        print("Инстанс успешно создан!")
    except Exception as e:
        print(f"Ошибка при создании: {e}")

if __name__ == "__main__":
    create_instance()
