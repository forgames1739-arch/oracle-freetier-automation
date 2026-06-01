#!/usr/bin/env python3
import oci
import os
import logging
import time
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
            return [ad.name for ad in response.data]
        except Exception as e:
            logger.error(f"Error getting ADs: {e}")
            return []

    def get_vcn_and_subnet(self, compartment_id):
        try:
            vcn_response = self.network_client.list_vcns(compartment_id=compartment_id)
            if not vcn_response.data:
                return None, None
            vcn_id = vcn_response.data[0].id

            subnet_response = self.network_client.list_subnets(
                compartment_id=compartment_id,
                vcn_id=vcn_id
            )
            if not subnet_response.data:
                return vcn_id, None
            return vcn_id, subnet_response.data[0].id
        except Exception as e:
            logger.error(f"Error getting VCN/Subnet: {e}")
            return None, None

    def create_instance(self, compartment_id, availability_domain, subnet_id):
        try:
            launch_details = oci.core.models.LaunchInstanceDetails(
                compartment_id=compartment_id,
                display_name="always-free-arm",
                image_id=self._get_ampere_image_id(compartment_id),
                shape="VM.Standard.A1.Flex",
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    vcpus=4,
                    memory_in_gbs=24
                ),
                availability_domain=availability_domain,
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    subnet_id=subnet_id,
                    assign_public_ip=True
                )
            )

            response = self.compute_client.launch_instance(launch_details)
            logger.info(f"✅ Instance created: {response.data.id}")
            return response.data.id
        except oci.exceptions.ServiceError as e:
            if "out of capacity" in str(e).lower():
                logger.warning("⚠ Out of capacity")
                return None
            else:
                logger.error(f"❌ Service error: {e}")
                raise
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            raise

    def _get_ampere_image_id(self, compartment_id):
        try:
            response = self.compute_client.list_images(
                compartment_id=compartment_id,
                shape="VM.Standard.A1.Flex",
                operating_system="Oracle Linux",
                operating_system_version="9"
            )
            if response.data:
                return response.data[0].id
            return None
        except Exception as e:
            logger.warning(f"Error getting image: {e}")
            return None

def create_instance():
    compartment_id = os.getenv("OCI_COMPARTMENT_OCID")
    subnet_id = os.getenv("OCI_SUBNET_OCID")

    if not compartment_id or not subnet_id:
        logger.error("❌ compartment_id or subnet_id missing")
        return

    creator = OracleInstanceCreator()

    while True:
        logger.info(f"\n--- Новая попытка ({datetime.now().strftime('%H:%M')}) ---")
        ads = creator.get_availability_domains(compartment_id)
        if not ads:
            logger.error("❌ Нет AD")
            time.sleep(60)
            continue

        vcn_id, sub = creator.get_vcn_and_subnet(compartment_id)
        if not sub:
            logger.error("❌ Нет subnet")
            time.sleep(60)
            continue

        ad = ads[0]
        logger.info(f"Используем AD: {ad}")

        instance_id = creator.create_instance(compartment_id, ad, sub)
        if instance_id:
            logger.info("🎉 СЕРВЕР СОЗДАН! УРА!")
            return
        else:
            logger.info("🔄 Нет capacity — ждём 60 секунд...")
            time.sleep(60)

if __name__ == "__main__":
    create_instance()
