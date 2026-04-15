import os, json, logging
from azure.identity import  get_bearer_token_provider
from openai import AzureOpenAI, APIError
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv
load_dotenv()
from azure.keyvault.secrets import SecretClient
from azure.appconfiguration.provider import (
    load,
    SettingSelector
)
from typing import Optional, Any

class GETGENERATEDRESPONSE:
    """
    
    """
    def __init__(self):
        self.keyvault_name = os.getenv('keyvault_url')
        self.kv_uri = f"https://{self.keyvault_name}.vault.azure.net"
        self.credential = ClientSecretCredential(
            tenant_id= os.getenv('AZURE_TENANT_ID'), # type: ignore
            client_id= os.getenv('AZURE_CLIENT_ID'), # type: ignore
            client_secret=os.getenv('AZURE_CLIENT_SECRET') # type: ignore
        )

        self.kv_client = SecretClient(vault_url=self.kv_uri, credential=self.credential)

        self.azure_openai_endpoint : str= self.get_kv_secrets('azure-endpoint')
        self.azure_openai_version : Optional[str]  = self.get_kv_secrets('api-version')
        self.deployment_name : Optional[str] = self.get_kv_secrets('deploymentname')
        self.app_config_endpoint : Optional[str] = self.get_kv_secrets('app-config-endpoint')
        self.config = load(endpoint = self.app_config_endpoint,  # type: ignore
                           credential = self.credential)
        

        self.get_query_intent = self.config['get_query_intent_prompt']
        # self.customer_queries_prompt = self.config['customer_queries_prompt']
        # self.case_info_query_prompt = self.config['case_info_query_prompt']
        self.repeated_offender_prompt = self.config['repeated_offender_prompt']
        # self.top_chunks_prompt = self.config['top_chunks_prompt']
        self.get_query_intent_temp = self.config['get_query_intent_temp']
        self.get_top_chunks_temp = self.config['get_top_chunks_temp']

        self.token_provider = get_bearer_token_provider(
                        self.credential,
                        "https://cognitiveservices.azure.com/.default"
                        )

        if not all([self.keyvault_name, self.azure_openai_endpoint,self.azure_openai_version,self.deployment_name,self.get_query_intent]):
            logging.error("azure  openai environment variables. are missing" )
            raise


        try :
            self.azure_model_client = AzureOpenAI(
                azure_endpoint= self.azure_openai_endpoint, 
                api_version=self.azure_openai_version,
                azure_ad_token_provider= self.token_provider
            )
        except Exception as e:
            logging.error(f'Error Initializing due to : {e}')
            raise 


    def get_kv_secrets(self, secret_name: str)->str:
            """
            get keyvault secrets 
            """

            try:
                return self.kv_client.get_secret(secret_name).value # type: ignore
            except Exception as e:
                print(f"Error fetching secret {secret_name}: {str(e)}")
                return ''
            

    def get_query_intent_type(self,user_query:str)->dict: # type: ignore

        """
        get the intent of the user_query
        
        """


        try:
            response = self.azure_model_client.chat.completions.create(
            model=self.deployment_name, # type: ignore
            messages=[
                {"role": "system", "content": self.get_query_intent +  "\nAlways respond with a valid JSON object."}, # type: ignore
                {"role": "user", "content": f'#user_query# is : {user_query}'}
            ],
            temperature=int(self.get_query_intent_temp),
            response_format={"type": "json_object"}
        )

            raw_output = response.choices[0].message.content
            json_output = json.loads(raw_output) # type: ignore
            logging.warning(f'nature of fraud is : {json_output}')
            return json_output
        
        except APIError as e:
            if e.status_code == 400 and "content_filter" in str(e): # type: ignore
                logging.error("Request blocked by content filter")
                return {'query_intent': 'null_intent'}
        except Exception as e:
            logging.error(f'Failed to get the nature of fraud due to : {e}')
            return {'query_intent': 'null_intent'}


    def get_query_response(self, user_query :str, query_intent_type:str, context : Any, relevant_prompt :str )-> Optional[str]:

        """
        get the query response 
        
        """
        try:
            response = self.azure_model_client.chat.completions.create(
            model=self.deployment_name, #type: ignore
            messages=[
                {"role": "system", "content": relevant_prompt+ f'##context## are :{context}'}, 
                {"role": "user", "content": f'#user_query# is : {user_query} and ##user_query_intent## is : {query_intent_type}'}
            ],
            temperature=int(self.get_top_chunks_temp),
            # response_format={"type": "json_object"}
        )

            raw_output = response.choices[0].message.content
            if isinstance(raw_output, str):
                json_output = raw_output
            # if isinstance(raw_output, json):
            #     json_output = json.loads(raw_output) # type: ignore
            # logging.warning(f'AI response is  is : {json_output}')
            return json_output
        except APIError as e:
            if e.status_code == 400 and "content_filter" in str(e): # type: ignore
                logging.error("Request blocked by content filter")
                return 'Please make sure that you query is regarding either Staff, customer or  employee'
        
        except Exception as e:
            logging.error(f'Failed to get the response due to  : {e}')
            return 'Failed to return the response'