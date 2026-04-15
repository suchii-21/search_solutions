import azure.functions as func
import logging, json
from get_ai_response import GETGENERATEDRESPONSE
from get_top_chunks import GETTOPCHUNKS
from urllib.parse import urlparse
from preview_file import PREVIEWFILES

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="get_case_info")
def get_case_info(req: func.HttpRequest) -> func.HttpResponse:

    try:
    #get user_query related 
        query = req.get_json()
        # query = req_body.get('query')
    except ValueError:
        # return func.HttpResponse(json.dumps({"message": "Invalid JSON body"}), status_code=400)
        return func.HttpResponse(json.dumps({"message": "Please enter a valid query regarding staff , customer or a particular case"}),
                                 status_code = 400,
                                 mimetype="application/json")

    #if no user query return 500
    if not query:
        return func.HttpResponse(json.dumps({"message": "Please enter a valid query regarding staff , customer or a particular case"}),
                                 status_code = 400,
                                 mimetype="application/json")
    
    #extract user_query, and roles, and id
    role = query.get('role')
    user_id =  query.get('user_id')
    user_query = query.get('user_query')

    #role validation
    non_confidential_role = ['Issuers', 'Reviewer','Investigator', 'Referrer']
    
    confidential_role = ['Unit Head', 'ICT', 'System Administrator', 'Whistle-blower Secretary']

    if role not in (confidential_role + non_confidential_role):
        logging.error(f'Entered role is : {role}, which is not a valid role')
        return func.HttpResponse(json.dumps({"message" : "Please Make sure that you have a valid role to , get the answer for the query you have entered"}),
                                 status_code= 400,
                                 mimetype= "application/json")

    #send the user_query to get the intent 
    try:
        ai_response= GETGENERATEDRESPONSE()
        get_intent = ai_response.get_query_intent_type(user_query)
        
        query_intent_type = get_intent['query_intent']
        if query_intent_type== 'null_intent':
            return func.HttpResponse(json.dumps({"message" : "Please enter a valid query regarding staff , customer or a particular case"}),
                                 status_code = 400,
                                 mimetype="application/json")
        
        
        #send the user_query to fetch the top chunks from the index 
        try:
            get_relevant_chunks = GETTOPCHUNKS().get_top_chunks(user_query)
        #     logging.warning(type(get_relevant_chunks))
        #     return func.HttpResponse(
        #         json.dumps({'chunks' :get_relevant_chunks}),          
        #         status_code= 200,
        #         mimetype="application/json"
        # )
            # logging.warning(get_relevant_chunks)

            #citation 
            seen = set() #unique url
            citations = [] # to store the url
            no_citation_count = 0 #keep count of no citations
            


            for citation in get_relevant_chunks:
                chunk_is_confidential = str(citation.get('confidential', '')).strip().lower() == 'true'

                # If chunk is confidential, only confidential roles get the citation
                if chunk_is_confidential and role in non_confidential_role:
                    no_citation_count += 1
                    continue 

                if citation['citations']:
                    path = urlparse(citation['citations']).path.lstrip('/')
                    if path not in seen:
                        seen.add(path)
                        citations.append(path)
                else:
                    no_citation_count += 1

            # If no citations found
            if not citations:
                citations = ['No Citations Found']

        except Exception as e:
            logging.error(f'Failed to classify the user query due to : {e}')
            return func.HttpResponse(json.dumps({'message':'Please enter a valid query' }),
                                    status_code = 500,
                                    mimetype="application/json")
        
        #check if the chunk is confidential or not
        def is_not_confidential(value):
            """
            Validating the chunk , if confidential or not
            returns false if false
            """
            if value is None:
                return False
            return str(value).strip().lower() == 'false'

        #get confidential data based on the role for case_related and the employee related search
        data: list[str] = []
        if query_intent_type in ['case_related', 'customer_related']:
            

            if role in non_confidential_role:
                for get_chunk_data in get_relevant_chunks:
                    if is_not_confidential(get_chunk_data['confidential']):
                        data.append(get_chunk_data['context'])
            else:
                data = [text['context'] for text in get_relevant_chunks]

            if not data:
                data.append('No data because, it is confidential')

            
            result = "\n\n".join(data)
            
        ##get response for the staff related search
        if query_intent_type == 'staff_related':
            # data: list[str] = []
            case_id = []
            if role in non_confidential_role:
                for get_chunk_data in get_relevant_chunks:
                    case_id.append(f"Confidential case id : {get_chunk_data['case_ref_id']}")
                    if is_not_confidential(get_chunk_data['confidential']):   ##for false
                        data.append(get_chunk_data['context'])
                    else:
                        #if data is confidential send only the case id 
                        data.extend(case_id)

            else:
               data = [text['context'] for text in get_relevant_chunks]
            result = "\n\n".join(data)
        
        try:
            get_preview_link = PREVIEWFILES()
            get_link = get_preview_link.get_blob_sas_url(citations)
        except Exception as e:
            logging.error(f'Failed to get the citations')
            
                    

        #if semantic chunks are there 
        if get_relevant_chunks:
            try:
                if query_intent_type in [ 'staff_related' , 'customer_related', 'case_related']:
                    logging.warning(f"sending to AI : {result}")
                    get_repeated_staff = ai_response.get_query_response(
                                                    user_query,
                                                    query_intent_type,
                                                    result,
                                                    ai_response.repeated_offender_prompt)
                    
                    final_response = {
                        'response' : get_repeated_staff,
                        'path' : citations,
                        'preview_link' : get_link
                    }

                    return func.HttpResponse(
                    json.dumps( final_response),          
                    status_code= 200,
                    mimetype="application/json"
            )
            
            except Exception as staff_err:
                logging.error(f'Error while fetching response from AI due to : {staff_err}')
                return func.HttpResponse(json.dumps('Please enter a valid query'),
                                 status_code = 400,
                                 mimetype="application/json")

            # try:
            #     #if the query is regarding customer
            #     if query_intent_type== 'customer_related': 
            #         get_customer_info = ai_response.get_query_response(user_query,get_relevant_chunks, ai_response.customer_queries_prompt)
            #         return func.HttpResponse(
            #         json.dumps({'chunks' :get_customer_info}),          
            #         status_code= 200,
            #         mimetype="application/json"
            # )
            # except Exception as customer_err:
            #     logging.error(f'Error while fetching response from AI due to : {customer_err}')
            #     return func.HttpResponse(json.dumps('Please enter a valid query'),
            #                      status_code = 400,
            #                      mimetype="application/json")

            # try:
            #     #if the query is regarding the case
            #     if query_intent_type== 'case_related':  
                                
            #         get_case_details = ai_response.get_query_response(user_query,get_relevant_chunks,ai_response.case_info_query)
            #         return func.HttpResponse(
            #         json.dumps({'chunks' :get_case_details}),          
            #         status_code= 200,
            #         mimetype="application/json"
            # )
                
            # except Exception as case_err:
            #     logging.error(f'Error while fetching response from AI due to : {case_err}')
            #     return func.HttpResponse(json.dumps({'message' : 'Please enter a valid query' }),
            #                      status_code = 400,
            #                      mimetype="application/json")
            

            return func.HttpResponse(
                json.dumps({"message": "Invalid intent type"}),
                status_code=400,
                mimetype="application/json"
            )
            

        else:
            return func.HttpResponse(json.dumps({'message' :'No releavnt data found for the query' }),
                                 status_code = 400,
                                 mimetype="application/json") 


    except Exception as e:
                logging.error(f'Failure to get the releavnt chunks due to : {e}')
                return func.HttpResponse(json.dumps('Please enter a valid query'),
                                    status_code = 400,
                                    mimetype="application/json")
    


   