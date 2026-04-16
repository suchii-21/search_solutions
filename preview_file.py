import os, json, logging
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv()
from urllib.parse import quote
import mimetypes
class PREVIEWFILES:
    """ 
    class to preview the files for 1 hour
    
    """

    def __init__(self) :
        self.keyvault_name = os.getenv('keyvault_url')
        self.kv_uri = f"https://{self.keyvault_name}.vault.azure.net"
        self.credential = ClientSecretCredential(
            tenant_id= os.getenv('AZURE_TENANT_ID'), # type: ignore
            client_id= os.getenv('AZURE_CLIENT_ID'), # type: ignore
            client_secret=os.getenv('AZURE_CLIENT_SECRET') # type: ignore
        )

        self.kv_client = SecretClient(vault_url=self.kv_uri, credential=self.credential)
        self.account_name = self.get_kv_secrets('blob-account-name')

    def get_kv_secrets(self, secret_name: str)->str:
        """
        get keyvault secrets 
        """

        try:
            return self.kv_client.get_secret(secret_name).value # type: ignore
        except Exception as e:
            print(f"Error fetching secret {secret_name}: {str(e)}")
            return ''


    def get_blob_sas_url(self, blob_path: list[str]) -> list[str]:
        preview_list: list[str] = []

        office_extensions = {'.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt'}
        office_viewer_url = "https://view.officeapps.live.com/op/view.aspx?src="

        account_url = f"https://{self.account_name}.blob.core.windows.net"
        blob_service_client = BlobServiceClient(account_url=account_url, credential=self.credential)

        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=1)
        user_delegation_key = blob_service_client.get_user_delegation_key(
            key_start_time=now,
            key_expiry_time=expiry
        )

        for blob in blob_path:

            if '/' not in blob:
                logging.warning(f"Skipping invalid blob path: {blob}")
                continue

            try:
                parts = blob.split('/', 1)
                container_name = parts[0]
                blob_name = parts[1]

                _, ext = os.path.splitext(blob_name.lower())
                content_type, _ = mimetypes.guess_type(blob_name)
                content_type = content_type or 'application/octet-stream'

                if ext in office_extensions:
                    sas_token = generate_blob_sas(
                        account_name=self.account_name,
                        container_name=container_name,
                        blob_name=blob_name,
                        user_delegation_key=user_delegation_key,
                        permission=BlobSasPermissions(read=True),
                        expiry=expiry,
                        start=now
                    )
                    raw_sas_url = f"{account_url}/{container_name}/{blob_name}?{sas_token}"
                    encoded_sas_url = quote(raw_sas_url, safe='')
                    sas_url = f"{office_viewer_url}{encoded_sas_url}"

                else:
                    sas_token = generate_blob_sas(
                        account_name=self.account_name,
                        container_name=container_name,
                        blob_name=blob_name,
                        user_delegation_key=user_delegation_key,
                        permission=BlobSasPermissions(read=True),
                        expiry=expiry,
                        start=now,
                        content_disposition="inline",
                        content_type=content_type
                    )
                    sas_url = f"{account_url}/{container_name}/{blob_name}?{sas_token}"

                preview_list.append(sas_url)

            except Exception as e:
                logging.error(f"Failed to generate SAS URL for {blob}: {e}")
                preview_list.append("Error generating preview URL")

        return preview_list


clss = PREVIEWFILES().get_blob_sas_url(['No citations found', 'adibstorageblobcontainer/case_1/Fraud_Report_Case_01.docx'])
print(clss)
# print(result)
