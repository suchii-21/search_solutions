import os,json,logging
from dotenv import load_dotenv
load_dotenv()
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
from azure.ai.textanalytics import TextAnalyticsClient
import re


categories_pii = {
    "Person":           "person",
    "PhoneNumber":      "phone",
    "PassportNumber":   "passport",
    "Email":            "email",
    "Address":          "address",
    "DateTime":         "dob",
    "CreditCardNumber": "credit_card",


    
}


custom_pii = {
    "staffid":  r'\bstaff\s*id\s*[:\-]?\s*\d{4,8}\b',
    "rimno":    r'\brim\s*no\.?\s*[:\-]?\s*\d{4,10}\b',
    "emiratesid": r'\b784-\d{4}-\d{7}-\d{1}\b', 
}



class PIIREDACTION:
    """ 
    Redacting PII before sending to LLM
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
        self.language_endpoint = self.get_kv_secrets('language-endpoint')

        self.ai_client = TextAnalyticsClient(endpoint=self.language_endpoint, credential=self.credential)

    def get_kv_secrets(self, secret_name: str)->str:
        """
        get keyvault secrets 
        """

        try:
            return self.kv_client.get_secret(secret_name).value # type: ignore
        except Exception as e:
            print(f"Error fetching secret {secret_name}: {str(e)}")
            return ''
    

    def redact_custom_pii(self, text: str, mapping: dict, counters: dict) -> str:
        for prefix, pattern in custom_pii.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                counters[prefix] = counters.get(prefix, 0) + 1
                placeholder = f"<{prefix}_{counters[prefix]}>"
                mapping[placeholder] = match.group()
                text = text.replace(match.group(), placeholder, 1)
        return text
        

    def redact_pii(self, texts: list[str]) -> list[dict]:

        """
        redact pii 
        
        """
        pii_results = self.ai_client.recognize_pii_entities(documents=texts)
        output = []

        for idx, pii_result in enumerate(pii_results):
            text = texts[idx]
            category_counters: dict[str, int] = {}
            mapping: dict[str, str] = {}

            if pii_result.is_error:
                output.append({"redacted_text": text, "mapping": {}})
                continue

            # Step 1: Azure built-in PII
            entities = sorted(pii_result.entities, key=lambda x: x.offset)
            redacted = ""
            last_idx = 0

            for entity in entities:
                redacted += text[last_idx: entity.offset]
                prefix = categories_pii.get(entity.category, entity.category.lower())
                category_counters[prefix] = category_counters.get(prefix, 0) + 1
                placeholder = f"<{prefix}_{category_counters[prefix]}>"
                mapping[placeholder] = text[entity.offset: entity.offset + entity.length]
                redacted += placeholder
                last_idx = entity.offset + entity.length

            redacted += text[last_idx:]

            # Step 2: Custom regex PII on top of already-redacted text
            redacted = self.redact_custom_pii(redacted, mapping, category_counters)

            output.append({"redacted_text": redacted, "mapping": mapping})

            logging.warning(f'redacted : {output}')

        return output




    def restore_pii(self, llm_response: str, get_mapped_value: dict) -> str:
        for placeholder, original in get_mapped_value.items():
            llm_response = llm_response.replace(placeholder, original)
        return llm_response
