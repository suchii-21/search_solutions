import os, json, logging
from dotenv import load_dotenv
load_dotenv()
from azure.keyvault.secrets import SecretClient
from azure.search.documents.models import (
    VectorizableTextQuery,
    QueryType,
    QueryAnswerType,
    QueryCaptionType
)
from typing import Optional
from azure.identity import ClientSecretCredential
from azure.search.documents import (SearchClient,SearchItemPaged)

class GETTOPCHUNKS:

    """
    Get top chunks semantically similar to the user Query
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

        self.kv_client = SecretClient(vault_url=self.kv_uri, credential=self.credential)
        self.index_name =  self.get_kv_secrets('get-index-name')
        self.search_endpoint = self.get_kv_secrets('get-search-endpoint')

        #validate the values 
        if not all([self.index_name, self.search_endpoint]):
            logging.error(f'Missing Values')

        self.search_client=SearchClient(endpoint=self.search_endpoint,credential=self.credential,index_name=self.index_name) # type: ignore



    def get_kv_secrets(self, secret_name:str)->Optional[str]:
        """
        get keyvault secrets 
        """

        try:
            return self.kv_client.get_secret(secret_name).value 
        except Exception as e:
            print(f"Error fetching secret {secret_name}: {str(e)}")
            return ''
        
    def get_top_chunks(self, user_query: str) -> list[dict]:
        """
        get top chunks related to the user_query
        """
        try:
            vector_query = VectorizableTextQuery(
                text=user_query,
                k=50,
                fields='text_vector',
                exhaustive=True
            )
            logging.warning('Query has been embedded')

            results = self.search_client.search(
                search_text=user_query,
                vector_queries=[vector_query],
                select=['title', 'chunk', 'confidential', 'source_link','case_ref_id'],
                query_type="semantic",
                semantic_configuration_name='legacy-semantic-config',
                query_caption="extractive",
                query_answer="extractive",
                query_answer_threshold=0.95,
                top=50
            )
            logging.warning('Got results')

            rernaker_threshold = 2.0  # Azure reranker scores ranges from 0-4, kept 2 after tuning

            final_response = []

            for result in results:
                reranker_score = result.get('@search.reranker_score') or 0

                # Skiping chunks which do not meet the threshold value
                if reranker_score < rernaker_threshold:
                    logging.warning(f"Skipping chunk with low reranker score: {reranker_score:.2f}")
                    continue

                response = {
                    "context": result.get('chunk', ''),
                    "citations": result["source_link"],
                    "confidential": result["confidential"],
                    "case_ref_id": result["case_ref_id"],
                    "reranker_score": reranker_score  
                }
                final_response.append(response)

            semantic_answers = results.get_answers()
            if semantic_answers:
                for ans in semantic_answers:
                    if ans.score >= 0.95:   # type: ignore
                        final_response.append({
                            "context": ans.text,
                            "citations": None,
                            "confidential": None,
                            "case_ref_id" : None
                        })
            logging.warning(final_response)
            return final_response

        
        except Exception as e:
            logging.error(f'Failure to get the top chunks due to : {e}')
            return [{"context" : "", "citations" : "","confidential" : "" , "case_ref_id" : ""}]

