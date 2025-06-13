import os
import json
import asyncio
import aiofiles  # Added for async file operations

from openai import AsyncOpenAI  # Changed to AsyncOpenAI
from tavily import AsyncTavilyClient
from sec_api import FullTextSearchApi
from gpt_researcher import GPTResearcher
import dart_fss as dart
import pandas as pd  # Assuming fs[i] is a pandas DataFrame for to_csv
from typing import Dict, Any
import streamlit as st
import uuid
from langchain_community.document_loaders import TextLoader
from langchain.chains import LLMChain, StuffDocumentsChain
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain.tools import Tool
from langchain.chat_models import init_chat_model

from dotenv import load_dotenv

load_dotenv()

# Ensure OPENAI_API_KEY is set in your environment variables or .env file
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SEC_API_KEY = os.getenv("SEC_API_KEY")
DART_API_KEY = os.getenv("DART_API_KEY")


# COMMENTED OUT: StreamlitLogHandler class for streaming logs
# class StreamlitLogHandler:
#     """
#     A custom logs handler for GPTResearcher that streams logs to a
#     Streamlit container.
#     """

#     def __init__(self, logs_container, report_container):
#         """
#         Initializes the handler with a Streamlit container.

#         Args:
#             container: A Streamlit container (e.g., returned by st.empty()).
#         """
#         self.logs_container = logs_container
#         self.report_container = report_container
#         self.logs = ""
#         self.report_content = ""
#         self.lock = asyncio.Lock()  # To handle async updates safely

#     async def send_json(self, data: Dict[str, Any]) -> None:
#         """
#         Receives JSON data from GPTResearcher and displays it in Streamlit.
#         This method is called by GPTResearcher during its process.
#         """
#         async with self.lock:
#             if data['type'] == 'report':
#                 try:
#                     # Extract a meaningful message or format the JSON
#                     if 'message' in data:
#                         message = data['message']
#                     elif 'output' in data:
#                         message = data['output']
#                     else:
#                         # Default to a formatted JSON string
#                         message = f"```json\n{json.dumps(data, indent=2)}\n```"

#                     # Append new log and update the container
#                     self.report_content += message + "\n\n"
#                     self.report_container.markdown(self.report_content)

#                 except Exception as e:
#                     # Fallback for any processing errors
#                     error_message = f"Error processing log: {e}\n{str(data)}\n\n"
#                     self.report_content += error_message
#                     self.report_container.warning(error_message)
#             else:
#                 try:
#                     # Extract a meaningful message or format the JSON
#                     if 'message' in data:
#                         message = data['message']
#                     elif 'output' in data:
#                         message = data['output']
#                     else:
#                         # Default to a formatted JSON string
#                         message = f"```json\n{json.dumps(data, indent=2)}\n```"

#                     # Append new log and update the container
#                     self.logs += message + "\n\n"
#                     self.logs_container.markdown(self.logs)

#                 except Exception as e:
#                     # Fallback for any processing errors
#                     error_message = f"Error processing log: {e}\n{str(data)}\n\n"
#                     self.logs += error_message
#                     self.logs_container.warning(error_message)


async def tavily_web_search(url, num_results=5):
    """Perform a web search using Tavily API and return relevant information asynchronously."""
    client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
    search_query = "Information about " + url + " and Top competitors of " + url + "with its Ticker"
    response = client.extract(urls=url)
    search_response = await client.search(
        query=search_query,
        search_depth="advanced",
        include_domains=[],
        exclude_domains=[],
        max_results=num_results,
        include_answer=True,
        include_raw_content=True,
        include_images=False
    )

    search_results = []
    if "results" in response:
        for result in response["results"]:
            search_results.append({
                "Company_Information": result.get("raw_content","No description found")
            })
    if "results" in search_response:
        for result in search_response["results"]:
            search_results.append({
                "Title": result.get("title", ""),
                "Link": result.get("url", ""),
                "Snippet": result.get("content", "No description found"),
                "Content": result.get("raw_content", ""),
                "Score": result.get("score", "")
            })
    return search_results


tools = [{
    "type": "function",
    "function": {
        "name": "tavily_web_search",  # This should match the async function name if used directly by OpenAI model
        "description": "Get information about the user prompt using Tavily web search",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {  # Parameter name changed from 'prompt' to 'query' to match tavily_web_search signature
                    "type": "string",
                    "description": "Web Search query"
                }
            },
            "required": ["query"],
            "additionalProperties": False
        },
        "strict": True  # Note: 'strict' is not a standard parameter for OpenAI function definitions.
        # It might be specific to a library or framework you're using it with.
        # If it's for OpenAI API, it's usually not needed.
    }
}]


async def generate_company_information(url, language):
    """Generate company information asynchronously."""
    system_prompt = f"""
    You will get a company or organization url link. Your job is to get company information.

    Generate these for each user query.

    1. Company Name.
    2. Name of Company's Industry.
    3. Carefully understand the industry of company and name Top 5 related industry competitors of Company.
    4. Generate all information 'company_name','description', 'company_first_name', "ticker", 'industry' and 'competitors'.
    5. Generate all information only in {language} language. Even if company name is in any translate it to {language} and give {language} name.
    
    Please respond ONLY with a JSON object in the following format (nothing else):
    {{
        "company_name": "Full Name of company",
        "company_first_name": "Only first name or first half of company",
        "ticker" : "Ticker of company",
        "description": "Company description",
        "industry": "Primary industry or sector",
        "competitors": ["Competitor 1", "Competitor 2", "Competitor 3", "Competitor 4", "Competitor 5"]
    }}
    """
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    # Initial call to determine if a tool (web search) is needed
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Give me information about this company {url}"}
        ],
        tools=tools,
        tool_choice="auto",
        response_format={"type": "json_object"}
    )

    msg = response.choices[0].message
    if msg.tool_calls:
        # --- Start of Changes ---
        messages_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Give me information about this company {url}"},
            msg,  # Include the assistant's message with tool_calls
        ]

        # Process each tool call
        for tool_call in msg.tool_calls:
            function_name = tool_call.function.name

            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                print(f"Error: Could not decode arguments for {function_name}: {tool_call.function.arguments}")
                # Optionally add an error tool message or skip
                messages_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps({"error": "Invalid arguments received."})
                })
                continue  # Move to the next tool call

            tool_output = None
            if function_name == "tavily_web_search":
                try:
                    # Use .get for safety, prefer "query"
                    query = arguments.get("query", arguments.get("prompt"))
                    if query:
                        tool_output = await tavily_web_search(query=query)
                    else:
                        tool_output = {"error": f"Missing 'query' argument for {function_name}."}
                except Exception as e:
                    tool_output = {"error": f"Error calling tavily_web_search: {str(e)}"}
            else:
                # Handle unknown tools if necessary
                tool_output = {"error": f"Unknown tool: {function_name}"}

            # Append the tool's response message
            messages_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": json.dumps(tool_output)  # Tool output must be a string
            })

        # Send the full history including tool responses back to the model
        followup = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages_history,  # Use the constructed history
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        # --- End of Changes ---

        content_str = followup.choices[0].message.content
        try:
            content = json.loads(content_str)
            return content
        except json.JSONDecodeError:
            return {"error": "Failed to parse JSON response from LLM after tool use.", "raw_content": content_str}

    # If no tool was called, parse and return the direct response
    if msg.content:
        try:
            content = json.loads(msg.content)
            return content
        except json.JSONDecodeError:
            return {"error": "Failed to parse initial JSON response from LLM.", "raw_content": msg.content}

    return {"error": "No content or tool call from LLM."}


async def get_dart_company_information(company_name, first_name):
    corp_list = dart.get_corp_list()
    corp = None

    # First try with full company name
    try:
        corp = corp_list.find_by_corp_name(company_name, exactly=True, market='YKNE')
        if not corp:
            corp = corp_list.find_by_corp_name(company_name, exactly=False, market='YKNE')
    except:
        pass

    # If not found, try with first name
    if not corp:
        try:
            corp = corp_list.find_by_corp_name(first_name, exactly=True, market='YKNE')
            if not corp:
                corp = corp_list.find_by_corp_name(first_name, exactly=False, market='YKNE')
        except:
            pass

    # If still not found, return None
    if not corp:
        return "This company is not in the dart list"

    corp_data = []
    for info in corp:
        corp_code = info.corp_code
        corp_info = dart.api.filings.get_corp_info(corp_code=corp_code)
        corp_data.append(corp_info)

    return corp_data


async def generate_corp_code(company_name, short_list_data,url):
    """Generate corporation code asynchronously."""
    # Ensure short_list_data is stringified if it's complex for the prompt
    short_list_str = json.dumps(short_list_data) if not isinstance(short_list_data, str) else short_list_data

    system_prompt = f"""
    1. You are given:
    - A target company name: '{company_name}'
    - A target company website URL: '{url}'
    - A list of potential corporations with information: '{short_list_str}'
    
    2. In the list of potential corporations with information you would file 'hm_url' Homepage_url in each list index.
    3. Compare the 'hm_url' for all list with the company website URL : '{url}' and whichever list index hm_url is exactly same or similar with website URL {url}. Give me that list index. 
    4. If no relevant 'hm_url' or Corporation found in the list return "N/A".
    
    Return only the index of list like 0,1,2 which matches the best. Nothing else just the index.
    """

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Give me the List index for {company_name} based on the provided list."}
        ],
        #response_format={"type": "json_object"}
    )
    try:
        #return json.loads(response.choices[0].message.content)
        return response.choices[0].message.content
    except json.JSONDecodeError:
        return {"corp_code": "N/A", "error": "Failed to parse JSON from LLM for corp_code."}


async def read_json_async(file_path):
    """Asynchronously read a JSON file."""
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
        return json.loads(content)
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return []  # Or raise an error, or return a specific error indicator
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}.")
        return []
    except Exception as e:
        print(f"Error reading JSON file {file_path}: {type(e).__name__}: {e}")
        return []


async def short_list(company_name, company_first_name):
    """
    Search for companies in a list that match either the full company name or first name.
    Loads the company list from corp_list.json file.

    Args:
        company_name (str): The full company name to search for
        company_first_name (str): The company's first name to search for if full name not found

    Returns:
        list: Matching company objects or a string message if none found
    """
    # Initialize empty list to store matching companies
    short_lists = []

    # Load the company list from file with UTF-8 encoding
    try:
        with open("corp_list.json", "r", encoding="utf-8") as f:
            lis = json.load(f)
    # except UnicodeDecodeError:
    #     # Try with a different encoding if UTF-8 fails
    #     try:
    #         with open("corp_list.json", "r", encoding="utf-8-sig") as f:
    #             lis = json.load(f)
    #     except Exception as e:
    #         print(f"Error loading JSON file: {type(e).__name__}: {e}")
    #         return "Error loading company list"
    except Exception as e:
        print(f"Error loading JSON file: {type(e).__name__}: {e}")
        return "Error loading company list"

    # First try with the full company name
    for corp in lis:
        try:
            # Convert the Corp object to a string
            corp_str = str(corp)
            # Check if company_name is in the string representation
            if company_name in corp_str:
                short_lists.append(corp)
        except Exception as e:
            print(f"Error processing item: {type(e).__name__}: {e}")

    # If no matches were found with the full name, try with the first name
    if len(short_lists) == 0:
        for corp in lis:
            try:
                # Convert the Corp object to a string
                corp_str = str(corp)
                # Check if company_first_name is in the string representation
                if company_first_name in corp_str:
                    short_lists.append(corp)
            except Exception as e:
                print(f"Error processing item: {type(e).__name__}: {e}")

    # If still empty after both searches, return message
    if len(short_lists) == 0:
        return "This company is not in the dart list"

    return short_lists


async def sec_search(company_name,ticker):
    """Asynchronously search SEC filings."""
    if ticker == 'N/A':
        ticker="corporation"

    fullTextSearchApi = FullTextSearchApi(api_key=SEC_API_KEY)
    query = {
        "query": f"{company_name} {ticker}",
        "formTypes": ['10-K','8-K','20-F','10-Q'],
        "startDate": '2020-01-01',
    }
    # Run synchronous SDK call in a thread
    filings = await asyncio.to_thread(fullTextSearchApi.get_filings, query)
    return filings


# MODIFIED: Removed streaming containers from function signature
async def sec_get_report(query: str, report_type: str, sources: list) -> tuple[str, list]:
    """Generate SEC report using GPTResearcher asynchronously."""
    # COMMENTED OUT: StreamlitLogHandler for streaming logs
    # logs_handler = StreamlitLogHandler(logs_container, report_container)

    query= query + f"-Add these SEC filings references from source url '{sources}' as well in references"
    # MODIFIED: Removed websocket parameter (streaming handler)
    researcher = GPTResearcher(query=query, report_type=report_type, source_urls=sources, complement_source_urls=False,
                               config_path="config.json")
    researcher.cfg.load_config("config.json")
    # COMMENTED OUT: Report container info messages
    # report_container.info("Starting research... This may take a few minutes. ⏳")

    #configuration=researcher.cfg.load_config("config.json")  # Or path to your config file
    # configuration['FAST_LLM'] = os.getenv("FAST_LLM", "anthropic:claude-3-5-haiku-latest")
    # configuration['SMART_LLM'] = os.getenv("SMART_LLM", "anthropic:claude-3-7-sonnet-latest")
    # configuration['STRATEGIC_LLM'] = os.getenv("STRATEGIC_LLM", "anthropic:claude-3-5-haiku-latest")
    # configuration['FAST_TOKEN_LIMIT'] = int(os.getenv("FAST_TOKEN_LIMIT", 15000))
    # configuration['SMART_TOKEN_LIMIT'] = int(os.getenv("SMART_TOKEN_LIMIT", 15000))
    # configuration['STRATEGIC_TOKEN_LIMIT'] = int(os.getenv("STRATEGIC_TOKEN_LIMIT", 15000))
    # configuration['SUMMARY_TOKEN_LIMIT'] = int(os.getenv("SUMMARY_TOKEN_LIMIT", 1200))
    # configuration['TOTAL_WORDS'] = int(os.getenv("TOTAL_WORDS", 3000))
    # configuration['MAX_SUBTOPICS'] = int(os.getenv("MAX_SUBTOPICS", 5))
    # Set any other necessary configurations if GPTResearcher needs them
    # e.g. researcher.cfg.set_openai_api_key(OPENAI_API_KEY) if not picked up from env by GPTResearcher

    #researcher.cfg._set_attributes(configuration)

    # COMMENTED OUT: Report container info messages
    # report_container.info("Starting research... This may take a few minutes. ⏳")
    await researcher.conduct_research()
    # report_container.info("Writing report... This may take a few minutes. ⏳")
    report = await researcher.write_report()
    research_images = []
    # report_container.info("Writing images... This may take a few minutes. ⏳")
    # research_images = researcher.get_research_images()

    # MODIFIED: Return empty string for logs since streaming is disabled
    return report, research_images, ""


def _save_dataframe_to_csv_sync(df, filename):
    """Synchronous helper to save dataframe to CSV."""
    df.to_csv(filename, sep='\t', index=False)


async def dart_search(corp_code, temp_dir):
    """Asynchronously search DART and save documents."""
    dart.set_api_key(api_key=DART_API_KEY)

    # These DART FSS calls are likely synchronous
    corp_list = await asyncio.to_thread(dart.corp.get_corp_list)
    company = await asyncio.to_thread(corp_list.find_by_corp_code, corp_code)

    if not company:
        print(f"Company with corp_code {corp_code} not found in DART.")
        return None  # Indicate failure

    try:
        fs_results = await asyncio.to_thread(company.extract_fs, bgn_de='20200101',report_tp="annual",dataset="web",last_report_only=False)
    except Exception as e:
        return None

    folder_name = os.path.join(temp_dir, f"{corp_code}_my_docs")
    # os.makedirs is synchronous but typically very fast.
    # For strict async, it could be wrapped with asyncio.to_thread or use an async os lib.
    os.makedirs(folder_name, exist_ok=True)

    save_tasks = []
    if fs_results:  # Check if fs_results is not None and is iterable
        for i, df in enumerate(fs_results):
            if isinstance(df, pd.DataFrame):  # Ensure it's a DataFrame
                filename = os.path.join(folder_name, f"dataframe_{i}.txt")
                # Use asyncio.to_thread for pandas I/O operation
                task = asyncio.to_thread(_save_dataframe_to_csv_sync, df, filename)
                save_tasks.append(task)
                print(f"Scheduled saving fs[{i}] to {filename}")
            else:
                print(f"Skipping fs[{i}] as it is not a DataFrame (type: {type(df)}).")
    else:
        print(f"No financial statements (fs_results) found or extracted for {corp_code}.")
        return None  # Or an empty path, depending on how you want to handle

    await asyncio.gather(*save_tasks)  # Wait for all save operations to complete

    print(f"All dataframes saved successfully in {folder_name} folder!")
    return folder_name


table_format="""
| **Business #**         | {BusinessNumber}            | **Corp Registration #**  | {CorpRegistrationNumber}    |
|------------------------|-----------------------------|--------------------------|-----------------------------|
| **CEO Name**           | {CEOName}                   | **Incorporation Date**   | {IncorporationDate}         |
| **Capital Stock**      | {CapitalStock}              | **# of Employees**       | {NumberOfEmployees}         |
| **Major Shareholders** | {MajorShareholders}         | **Company Type**         | {CompanyType}               |
| **Financial Audit**    | {FinancialAudit}            |                          |                             |
| **Line of Business**   | {LineOfBusiness}            |                          |                             |
| **Address**            | {Address}                   |                          |                             |


| **Year** | **Corporate History Details**(If available)|
|----------|--------------------------------------------|
| 2025     | {History_2025}                             |
| 2023     | {History_2023}                             |
| 2021     | {History_2021}                             |
| 2017     | {History_2017}                             |
| 2010     | {History_2010}                             |
| 2000     | {History_2000}                             |
| 1993     | {History_1993}                             |
| 1980s    | {History_1980s}                            |

"""
table_data="""

Business # : ""
CEO NAME : ""
CAPITAL STOCK : ""
MAJOR SHAREHOLDERS : ""
FINANCIAL AUDIT : ""
LINE OF BUSINESS : ""
ADDRESS : ""
CORPORATE HISTORY : ""
CORP CODE : ""
INCORPORATION DATE : ""
NUMBER OF EMPLOYEES : ""
COMPANY TYPE : ""

"""
# MODIFIED: Removed streaming containers from function signature
async def dart_get_report(query: str, report_source:str, path: str) -> tuple[str, list]:
    """Generate DART report using GPTResearcher asynchronously."""
    # if not path: # Handle case where dart_search might have returned None
    #     return "Error: Document path not available for DART report generation.", [], ""

    if path:
        query = f"""
                Use this tone for report generation : Simple/Factual tone
                {query} 
                -In References, Must include Dart fss **ANNUAL REPORT** filing of company.

                For the first page of report add Table with this data {table_data} put the value and information of these after you generate the report and have their value.
                Table format should be like this: {table_format}
                if you dont have any value for them then write "N/A" in table. 
                if Corporate History data is not available of some years then just write those which are available.
                """
        os.environ['DOC_PATH'] = path  # GPTResearcher might pick this up
        researcher = GPTResearcher(query=query, report_type="research_report", report_source="hybrid",
                                   config_path="config_kr.json")
        researcher.cfg.load_config("config_kr.json")  # Or path to your config file
        await researcher.conduct_research()
        report = await researcher.write_report()
        research_images = []
        return report, research_images, ""
    else:
        query = f"""
                Use this tone for report generation : Simple/Factual tone
                {query} 
                
                For the first page of report add Table with this data {table_data} put the value and information of these after you generate the report and have their value.
                Table format should be like this: {table_format}
                if you dont have any value for them then write "N/A" in table. 
                if Corporate History data is not available of some years then just write those which are available.
                """
        researcher = GPTResearcher(query=query, report_type="research_report",config_path="config_kr.json")
        researcher.cfg.load_config("config_kr.json")
        await researcher.conduct_research()
        report = await researcher.write_report()
        research_images = []
        return report, research_images, ""


    # COMMENTED OUT: StreamlitLogHandler for streaming logs
    # logs_handler = StreamlitLogHandler(logs_container, report_container)

    # MODIFIED: Removed websocket parameter (streaming handler)



    # COMMENTED OUT: Report container info messages
    # report_container.info("Starting research... This may take a few minutes. ⏳")
    # report_container.info("Writing report... This may take a few minutes. ⏳")

    # report_container.info("Generating report images... This may take a few minutes. ⏳")
    # research_images = researcher.get_research_images()

    # MODIFIED: Return empty string for logs since streaming is disabled
    # return report, research_images, ""

