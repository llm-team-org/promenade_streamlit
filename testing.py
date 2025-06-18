#######---------ALL DART FUNCTIONS IN THIS FILE------#########

import os
import json
import asyncio
from gpt_researcher import GPTResearcher
from prom_functions import generate_company_information
from openai import AsyncOpenAI  # Changed to AsyncOpenAI
import dart_fss as dart
import pandas as pd  # Assuming fs[i] is a pandas DataFrame for to_csv
import shutil

from langchain_community.document_loaders import TextLoader
from langchain.chains import LLMChain, StuffDocumentsChain
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain.tools import Tool
from langchain.chat_models import init_chat_model

from dotenv import load_dotenv

load_dotenv()

# Ensure OPENAI_API_KEY is set in your environment variables or .env file
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DART_API_KEY = os.getenv("DART_API_KEY")


def _save_dataframe_to_csv_sync(df, filename):
    """Synchronous helper to save dataframe to CSV."""
    df.to_csv(filename, sep='\t', index=False)

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
        return "N/A"

    corp_data = []
    for info in corp:
        corp_code = info.corp_code
        corp_info = dart.api.filings.get_corp_info(corp_code=corp_code)
        corp_data.append(corp_info)

    return corp_data


async def generate_corp_code(company_name, short_list_data, url):
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
        # response_format={"type": "json_object"}
    )
    try:
        # return json.loads(response.choices[0].message.content)
        return response.choices[0].message.content
    except json.JSONDecodeError:
        return {"corp_code": "N/A", "error": "Failed to parse JSON from LLM for corp_code."}


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


table_format = """
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
table_data = """

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
async def dart_get_report(query: str, report_source: str, path: str) -> tuple[str, list]:
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
        researcher = GPTResearcher(query=query, report_type="research_report", config_path="config_kr.json")
        researcher.cfg.load_config("config_kr.json")
        await researcher.conduct_research()
        report = await researcher.write_report()
        research_images = []
        return report, research_images, ""

async def dart_tool_calling(url, query):
    # """
    # Retrieves DART annual report filing information for the korean based companies specified by the user's input URL.
    # When user asked any query related to dart annual report filing.
    #
    # Args:
    #     url: Company url:
    #     query: Query of user:
    # """
    company_info=await generate_company_information(url,language="korean")
    company_full_name=company_info["company_name"]
    company_first_name=company_info["company_first_name"]
    company_short_list = await get_dart_company_information(company_full_name, company_first_name)
    print(company_short_list)
    corp_list_index = await generate_corp_code(company_full_name, company_short_list, url)
    print("corp list = " ,corp_list_index)
    if corp_list_index == "N/A":
        print("No corp code is found")
    else:
        index = int(corp_list_index)
        company_list=company_short_list[index]
        corp_code=company_list["corp_code"]
        print("corp code = ", corp_code)

        temp_dir = "temporary"
        os.makedirs(temp_dir, exist_ok=True)
        folder = await dart_search(corp_code, temp_dir)
        files = os.listdir(folder)
        documents = []

        if files:
            for file_name in files:
                file_path = os.path.join(folder, file_name)
                if file_path.endswith(".txt"):
                    loader = TextLoader(file_path, encoding='utf-8')
                    documents.extend(loader.load())  # Loads list of Document objects

        if documents:
            document_prompt = PromptTemplate(
                input_variables=["page_content"], template="{page_content}"
            )
            document_variable_name = "context"

            # Modified prompt to include the query for relevant content extraction
            prompt = ChatPromptTemplate.from_template(
                "Based on the following context, answer this query: {query}\n\nContext: {context}"
            )

            llm = init_chat_model("gpt-4.1-mini", model_provider="openai")

            llm_chain = LLMChain(llm=llm, prompt=prompt)
            chain = StuffDocumentsChain(
                llm_chain=llm_chain,
                document_prompt=document_prompt,
                document_variable_name=document_variable_name,
            )

            # Execute the chain with the query to get the relevant content
            result = chain.run(input_documents=documents, query=query)
            shutil.rmtree("temporary")
            return result
        else:
            return "No documents found"

# def get_dart_tool_calling():
#     description = """
#     Retrieves DART annual report filing information for the korean based companies specified by the user's input URL.
#     When user asked any query related to dart annual report filing.
#     """
#
#     return Tool(name="dart_tool_calling", func=dart_tool_calling, description=description)

tools= [dart_tool_calling]
llm = init_chat_model("gpt-4.1-mini", model_provider="openai")
llm_with_tools = llm.bind_tools(tools)
query="Url of company is: https://www.woongjin.co.kr/. What is quarter report of 2024."
ans=llm_with_tools.invoke(query)
print(ans)

async def execute_async_tool():
    if ans.tool_calls:
        tool_call = ans.tool_calls[0]
        func_name = tool_call['name']
        args = tool_call['args']

        print(f"Function: {func_name}")
        print(f"Arguments: {args}")

        # Since dart_tool_calling is async, use await
        if func_name == 'dart_tool_calling':
            result = await dart_tool_calling(**args)
            print(f"Result: {result}")
            return result


# Run the async execution
result = asyncio.run(execute_async_tool())
print(result)
# ans = asyncio.run(dart_tool_calling('https://www.woongjin.co.kr/', '2024 quarter report'))
# print(ans)
