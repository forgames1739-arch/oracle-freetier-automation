import oci
import os
import logging
import time
from datetime import datetime

# ====================== ЛОГИРОВАНИЕ (максимум логов) ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ====================== КЛАСС ДЛЯ ЧИСТОГО КОДА ======================
class OracleInstanceCreator:
    def __init__(self):
        self.config = {
            "user": os.getenv("OCI_USER_OCID"),
            "key_content": os.getenv("OCI_PRIVATE_KEY"),
            "fingerprint": os.getenv("OCI_FINGERPRINT"),
            "tenancy": os.getenv("OCI_TENANCY_OCID"),
            "region": os.getenv("OCI_REGION")
        }
        if not all(self.config.values()):
            raise ValueError("❌ Отсутствуют переменные окружения OCI!")

        self.compute_client = oci.core.ComputeClient(self.config)
        self.identity_client = oci.identity.IdentityClient(self.config)
        self.network_client = oci.core.VirtualNetworkClient(self.config)

    def get_availability_domains(self, compartment_id):
        try:
            response = self.identity_client.list_availability_domains(compartment_id=compartment_id)
            logger.info(f"✅ Получено {len(response.data)} Availability Domain")
            return [ad.name for ad in response.data]
        except Exception as e:
            logger.error(f"❌ Ошибка получения AD: {e}")
            return []

    def get_vcn_and_subnet(self, compartment_id):
        try:
            vcn_response = self.network_client.list_vcns(compartment_id=compartment_id)
            if not vcn_response.data:
                logger.warning("⚠️ VCN не найден")
                return None, None
            vcn_id = vcn_response.data[0].id

            subnet_response = self.network_client.list_subnets(compartment_id=compartment_id, vcn_id=vcn_id)
            if not subnet_response.data:
                logger.warning("⚠️ Подсеть не найдена")
                return vcn_id, None
            subnet_id = subnet_response.data[0].id
            logger.info(f"✅ Подсеть: {subnet_id[:20]}...")
            return vcn_id, subnet_id
        except Exception as e:
            logger.error(f"❌ Ошибка получения VCN/Subnet: {e}")
            return None, None

    def _get_image_id(self, compartment_id):
        try:
            response = self.compute_client.list_images(
                compartment_id=compartment_id,
                shape="VM.Standard.A1.Flex",
                operating_system="Oracle Linux",
                operating_system_version="9"
            )
            if response.data:
                img = response.data[0]
                logger.info(f"✅ Образ найден: {img.display_name} (OCID: {img.id[:20]}...)")
                return img.id
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения образа: {e}")
            return None

    def create_instance(self, compartment_id, availability_domain, subnet_id):
        try:
            shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
                vcpus=4,
                memory_in_gbs=24
            )

            launch_details = oci.core.models.LaunchInstanceDetails(
                compartment_id=compartment_id,
                availability_domain=availability_domain,
                display_name="always-free-arm",
                image_id=self._get_image_id(compartment_id),
                shape="VM.Standard.A1.Flex",
                shape_config=shape_config,
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    subnet_id=subnet_id,
                    assign_public_ip=True
                )
            )

            response = self.compute_client.launch_instance(launch_details)
            opc_id = response.headers.get("opc-request-id", "неизвестен")
            logger.info(f"✅ Сервер успешно создан! OPC-Request-ID: {opc_id}")
            return True

        except oci.exceptions.ServiceError as e:
            if "out of capacity" in str(e).lower():
                logger.warning(f"🔄 Охота продолжается: {e.message}")
                return False
            else:
                logger.error(f"❌ ServiceError: {e.message}")
                raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка: {e}")
            raise


# ====================== ОСНОВНАЯ ФУНКЦИЯ ======================
def create_instance():
    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    if not compartment_id or not subnet_id:
        logger.error("❌ compartment_id или subnet_id отсутствуют в .env")
        return

    creator = OracleInstanceCreator()

    while True:
        logger.info(f"\n🚀 Новая попытка ({datetime.now().strftime('%H:%M:%S')})")
        logger.info("🔄 Получение Availability Domain...")
        ads = creator.get_availability_domains(compartment_id)
        if not ads:
            logger.error("❌ Нет доступных AD")
            time.sleep(60)
            continue

        logger.info("🔄 Получение VCN и подсети...")
        vcn_id, sub = creator.get_vcn_and_subnet(compartment_id)
        if not sub:
            logger.error("❌ Нет подсети")
            time.sleep(60)
            continue

        ad = ads[0]
        logger.info(f"🎯 Выбран AD: {ad}")

        logger.info("🔄 Создание инстанса...")
        if creator.create_instance(compartment_id, ad, sub):
            logger.info("🎉 УРА! Сервер создан! Отправка в Telegram...")
            # Здесь можно добавить отправку в Telegram (уже есть в старом коде)
            return  # успешный запуск
        else:
            logger.info("⏳ Нет capacity — ждём 60 секунд...")
            time.sleep(60)


# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    create_instance()
