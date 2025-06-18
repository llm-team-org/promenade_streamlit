import logging
import asyncio
import json
import os
import shutil
import tempfile
from typing import TypedDict
import hashlib
import time

import dart_fss as dart
from dotenv import load_dotenv

from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_community.document_loaders import TextLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import tool
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langchain_openai import ChatOpenAI

from pydantic import BaseModel, Field
from typing import List, Optional

from openai import AsyncOpenAI
import pandas as pd
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from threading import RLock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Ensure API keys are set
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DART_API_KEY = os.getenv("DART_API_KEY")

# Configure caching - TTL cache that expires after 1 hour (3600 seconds)
# This will cache DART API responses to avoid repeated downloads
cache_lock = RLock()
dart_cache = TTLCache(maxsize=100, ttl=3600)  # Cache for 1 hour
company_info_cache = TTLCache(maxsize=50, ttl=1800)  # Cache for 30 minutes
corp_list_cache = TTLCache(maxsize=10, ttl=7200)  # Cache for 2 hours

class OriginalDocuments(TypedDict):
    title: str
    content: str


class ToolSource(TypedDict):
    source_type: str
    source_content: str
    source_path: str
    original_documents: list[OriginalDocuments]


class CompanyInfo(TypedDict):
    company_name: str
    company_first_name: str


def create_cache_key(*args, **kwargs):
    """Create a unique cache key from arguments."""
    key_parts = []
    for arg in args:
        if isinstance(arg, str):
            key_parts.append(arg)
        else:
            key_parts.append(str(arg))

    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")

    # Create hash of the key to ensure it's hashable and reasonable length
    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


@tool
def tavily_web_search(query: str) -> dict:
    """Use Tavily to search web information about a company."""
    tavily = TavilySearchResults()
    print("Tool Use:", query)
    return tavily.invoke({"query": query})


# --- Cached DART Functions ---

@cached(cache=corp_list_cache, lock=cache_lock, key=lambda: "corp_list")
def get_cached_corp_list():
    """Get and cache the DART corporation list."""
    logger.info("Fetching DART corporation list from API (not cached)")
    dart.set_api_key(api_key=DART_API_KEY)
    return dart.corp.get_corp_list()


@cached(cache=dart_cache, lock=cache_lock,
        key=lambda company_name, first_name: create_cache_key("corp_info", company_name, first_name))
def get_cached_dart_company_information(company_name: str, first_name: str) -> list | str:
    """
    Cached version of DART company information retrieval.
    Returns a list of corporation data or "N/A" if no information is found.
    """
    logger.info(f"Fetching DART company info for {company_name} (not cached)")

    corp_list = get_cached_corp_list()
    corp = None

    # Try with full company name first
    try:
        corp = corp_list.find_by_corp_name(company_name, exactly=True, market="YKNE")
        if not corp:
            corp = corp_list.find_by_corp_name(company_name, exactly=False, market="YKNE")
    except (ValueError, ConnectionError, TimeoutError) as e:
        logger.warning(f"Error finding company by full name '{company_name}': {e}")

    # If not found, try with first name
    if not corp:
        try:
            corp = corp_list.find_by_corp_name(first_name, exactly=True, market="YKNE")
            if not corp:
                corp = corp_list.find_by_corp_name(first_name, exactly=False, market="YKNE")
        except (ValueError, ConnectionError, TimeoutError) as e:
            logger.warning(f"Error finding company by first name '{first_name}': {e}")

    if not corp:
        logger.info(f"No corporation found for company name '{company_name}' or first name '{first_name}'.")
        return "N/A"

    corp_data = []
    for info in corp:
        corp_code = info.corp_code
        try:
            corp_info = dart.api.filings.get_corp_info(corp_code=corp_code)
            corp_data.append(corp_info)
        except (ValueError, ConnectionError, TimeoutError) as e:
            logger.error(f"Failed to retrieve corporation info for corp_code {corp_code}: {e}")

    return corp_data


@cached(cache=dart_cache, lock=cache_lock,
        key=lambda corp_code, beginning_date, ending_date: create_cache_key("dart_search", corp_code, beginning_date,ending_date))
def get_cached_dart_financial_statements(corp_code: str, beginning_date: str,ending_date: str) -> tuple[list, list]:
    """
    Cached version of DART financial statements retrieval.
    Returns tuple of (fs_results, original_documents_data
    """
    logger.info(f"Fetching DART financial statements for corp_code {corp_code} (not cached)")

    dart.set_api_key(api_key=DART_API_KEY)
    corp_list = get_cached_corp_list()
    company = corp_list.find_by_corp_code(corp_code)

    if not company:
        logger.warning(f"Company with corp_code {corp_code} not found in DART.")
        return [], []

    try:
        fs_results = company.extract_fs(
            bgn_de=beginning_date,
            end_de=ending_date,
            report_tp="annual",
            dataset="web",
            last_report_only=False
        )
    except (ValueError, ConnectionError, TimeoutError) as e:
        logger.error(f"Failed to extract financial statements for corp_code {corp_code}: {e}")
        return [], []

    # Convert DataFrames to serializable format for caching
    original_documents_data = []
    processed_fs_results = []

    if fs_results:
        for i, df in enumerate(fs_results):
            if isinstance(df, pd.DataFrame):
                # Store the dataframe as a dictionary for caching
                df_dict = df.to_dict('records')
                processed_fs_results.append({
                    'index': i,
                    'data': df_dict,
                    'columns': list(df.columns)
                })

                # Convert DataFrame to markdown and add to original documents
                title = f"Financial Statement {i + 1}"
                markdown_content = _convert_dataframe_to_markdown(df, title)
                original_documents_data.append({
                    'title': title,
                    'content': markdown_content
                })
            else:
                logger.info(f"Skipping financial statement {i} as it is not a DataFrame (type: {type(df)}).")
    else:
        logger.info(f"No financial statements found or extracted for {corp_code}.")

    return processed_fs_results, original_documents_data


# --- Main Function ---
@cached(cache=company_info_cache, lock=cache_lock, key=lambda url: create_cache_key("company_info", url))
async def get_cached_company_information(url: str) -> dict:
    """Cached version of company information retrieval using LangChain structured output."""

    system_prompt = """
    너는 사용자가 제공한 회사 URL로부터 회사 정보를 추출하는 AI이다.

    URL을 참고하여 회사의 전체 이름과 앞부분 이름을 한국어로 추출하라.
    영어 이름이라도 반드시 한국어로 번역해서 반환해야 한다.
    """

    tavily_tool = convert_to_openai_tool(tavily_web_search)

    llm = ChatOpenAI(model="gpt-4.1-nano", temperature=0.4, api_key=os.getenv("OPENAI_API_KEY"))
    llm_with_tools = llm.bind_tools([tavily_tool])
    llm_with_output = llm_with_tools.with_structured_output(CompanyInfo)
    llm = llm_with_output

    try:
        result = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=f"다음 회사 정보를 제공해 줘: {url}")])
        logger.info("Successfully retrieved company information (cached).")
        return result
    except (ValueError, RuntimeError) as e:
        logger.exception("Error during structured company info generation.")
        return {"error": str(e)}


def _save_dataframe_to_csv_sync(df: pd.DataFrame, filename: str):
    """Synchronously saves a pandas DataFrame to a CSV file."""
    df.to_csv(filename, sep="\t", index=False)


def _convert_dataframe_to_markdown(df: pd.DataFrame, title: str) -> str:
    """Convert pandas DataFrame to markdown format with robust error handling."""
    try:
        markdown_content = f"# {title}\n\n"

        # Check if DataFrame is empty
        if df.empty:
            markdown_content += "No data available.\n"
            return markdown_content

        # Try pandas to_markdown first (available in pandas >= 1.0.0)
        if hasattr(df, 'to_markdown'):
            try:
                markdown_content += df.to_markdown(index=False)
                return markdown_content
            except Exception as e:
                logger.warning(f"pandas to_markdown failed: {e}, falling back to manual conversion")

        # Manual markdown conversion as fallback
        # Create header
        headers = list(df.columns)
        markdown_content += "| " + " | ".join(str(header) for header in headers) + " |\n"
        markdown_content += "|" + "|".join([" --- " for _ in headers]) + "|\n"

        # Add rows
        for _, row in df.iterrows():
            row_values = []
            for value in row:
                # Handle different data types and None values
                if pd.isna(value):
                    row_values.append("")
                elif isinstance(value, (int, float)):
                    if pd.isna(value):
                        row_values.append("")
                    else:
                        row_values.append(str(value))
                else:
                    # Convert to string and escape pipe characters
                    str_value = str(value).replace("|", "\\|")
                    row_values.append(str_value)

            markdown_content += "| " + " | ".join(row_values) + " |\n"

        return markdown_content

    except Exception as e:
        logger.error(f"Error converting DataFrame to markdown: {e}")
        logger.error(f"DataFrame shape: {df.shape}, columns: {list(df.columns)}")

        # Return basic information about the DataFrame
        return f"""# {title}

**Error occurred during markdown conversion**

- DataFrame Shape: {df.shape}
- Columns: {list(df.columns)}
- Error: {str(e)}

**Sample Data (first 5 rows as string representation):**
```
{df.head().to_string()}
```
"""


async def get_dart_company_information(company_name: str, first_name: str) -> list | str:
    """
    Wrapper function that uses cached DART company information retrieval.
    """
    # Use cached version in a thread to avoid blocking
    return await asyncio.to_thread(get_cached_dart_company_information, company_name, first_name)


async def generate_corp_code(company_name: str, short_list_data: list | str, url: str) -> str:
    """
    Generates a corporation code by comparing the company's website URL
    with the homepage URLs in the provided list of potential corporations.
    """
    short_list_str = json.dumps(short_list_data) if not isinstance(short_list_data, str) else short_list_data

    system_prompt = (
        f"1. You are given:\n"
        f"- A target company name: '{company_name}'\n"
        f"- A target company website URL: '{url}'\n"
        f"- A list of potential corporations with information: '{short_list_str}'\n\n"
        f"2. In the list of potential corporations with information you will find 'hm_url' "
        f"(Homepage_url) in each list index.\n"
        f"3. Compare the 'hm_url' for all lists with the company website URL: '{url}'. "
        f"Identify the list index where 'hm_url' is exactly the same or similar to the "
        f"website URL {url}.\n"
        f"4. If no relevant 'hm_url' or Corporation is found in the list, return \"N/A\".\n\n"
        f"Return only the index of the list (e.g., 0, 1, 2) that matches the best. "
        f"Do not return anything else."
    )

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model="gpt-4.1-nano",  # Changed to gpt-4.1-nano
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Give me the List index for {company_name} based on the provided list."},
        ],
    )
    try:
        return response.choices[0].message.content.strip()
    except (IndexError, AttributeError) as e:
        logger.error(f"Failed to get corporation code from LLM: {e}")
        return "N/A"


async def dart_search(corp_code: str, temp_dir: str, beginning_date="20200101",ending_date="20250101") -> tuple[
    str | None, list[OriginalDocuments]]:
    """
    Uses cached DART financial statements and saves them as text files in a temporary directory.
    Returns both the folder path and original documents in markdown format.
    """
    # Get cached financial statements
    processed_fs_results, original_documents_data = await asyncio.to_thread(
        get_cached_dart_financial_statements, corp_code, beginning_date,ending_date
    )

    if not processed_fs_results:
        logger.info(f"No financial statements found or extracted for {corp_code}.")
        return None, []

    folder_name = os.path.join(temp_dir, f"{corp_code}_my_docs")
    os.makedirs(folder_name, exist_ok=True)
    logger.info(f"Created directory for DART documents: {folder_name}")

    save_tasks = []
    original_documents = []

    # Convert cached data back to DataFrames and save
    for fs_data in processed_fs_results:
        df = pd.DataFrame(fs_data['data'])
        df.columns = fs_data['columns']

        filename = os.path.join(folder_name, f"dataframe_{fs_data['index']}.txt")
        task = asyncio.to_thread(_save_dataframe_to_csv_sync, df, filename)
        save_tasks.append(task)
        logger.info(f"Scheduled saving financial statement {fs_data['index']} to {filename}")

    # Convert original documents data back to proper format
    for doc_data in original_documents_data:
        original_documents.append(OriginalDocuments(
            title=doc_data['title'],
            content=doc_data['content']
        ))

    await asyncio.gather(*save_tasks)
    logger.info(f"All dataframes saved successfully in {folder_name} folder.")
    return folder_name, original_documents


async def _process_company_info(url: str) -> tuple[str, str, str]:
    """Process company information from URL and return company names."""
    company_info = await get_cached_company_information(url)
    company_full_name = company_info.get("company_name")
    company_first_name = company_info.get("company_first_name")

    if not company_full_name:
        logger.error(f"Could not extract company full name from URL: {url}")
        raise ValueError("Could not retrieve company information.")

    return company_full_name, company_first_name, url


async def _get_corp_code(company_full_name: str, company_short_list: list, url: str) -> str:
    """Get corporation code from company information."""
    corp_list_index = await generate_corp_code(company_full_name, company_short_list, url)
    logger.info(f"Determined corporation list index: {corp_list_index}")

    if corp_list_index == "N/A":
        logger.info("No corporation code is found based on the provided URL and company list.")
        raise ValueError("No relevant corporation information found to generate a report.")

    try:
        index = int(corp_list_index)
        company_list_entry = company_short_list[index]
        corp_code = company_list_entry.get("corp_code")
        logger.info(f"Selected corporation code: {corp_code}")
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse corp list index or access company list entry: {e}")
        raise ValueError("Error processing company information.") from e

    if not corp_code:
        logger.error("Corporation code is missing.")
        raise ValueError("Failed to identify a valid corporation code for report generation.")

    return corp_code


async def _load_documents(folder_path: str) -> list:
    """Load documents from the folder path."""
    documents = []
    if folder_path and os.path.exists(folder_path):
        for file_name in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file_name)
            if file_path.endswith(".txt"):
                try:
                    loader = TextLoader(file_path, encoding="utf-8")
                    documents.extend(loader.load())
                    logger.info(f"Loaded document: {file_path}")
                except (UnicodeDecodeError, FileNotFoundError, IOError) as e:
                    logger.error(f"Error loading document {file_path}: {e}")
    else:
        logger.info("No documents found in the DART search results or folder not created.")
    return documents


async def _generate_report(documents: list, query: str) -> str:
    """Generate report from documents using LLM."""
    if not documents:
        return "No relevant DART documents were found or processed to answer your query."

    prompt = ChatPromptTemplate.from_template(
        """Extract all information relevant to the following query from the file content provided.

---

**Query:**
{query}

---

**File Content:**
{context}

---

**Instructions:**

* Present the extracted information in **professional, corporate documentation style**.
* Use **Markdown formatting** to structure the response effectively:

  * Use `##` for major sections and `###` for sub-sections
  * Use bullet points or numbered lists to itemize key details
  * Use tables where structured data presentation is appropriate
  * Emphasize important terms using **bold** or *italic* formatting as necessary
* Maintain the **same language** as the original file content.
* The final response must be a **standalone, authoritative answer** to the query:

  * Do **not** reference the source content directly
  * Do **not** use phrases like "Based on the document" or "According to the file"
* Write clearly, concisely, and in a tone suitable for professional or corporate audiences."""
    )


    llm = ChatOpenAI(model="gpt-4.1-nano", api_key=OPENAI_API_KEY)
    chain = create_stuff_documents_chain(llm, prompt=prompt)

    try:
        result = chain.invoke({"context": documents, "query": query})
        logger.info("Successfully generated report from DART documents.")
        return result

    except (ValueError, RuntimeError) as e:
        logger.error(f"Error generating report from documents: {e}")
        return "An error occurred while generating the report from the documents."


async def dart_tool_calling(url: str, query: str, beginning_date: str, ending_date:str) -> ToolSource:
    """
    Retrieves DART annual report filing information for the korean based companies specified by the user's input URL.
    When user asked any query related to dart annual report filing.
    Make sure beginning_date and ending date have at least of 6 months of difference like if beginning_date is (YYYYMMDD)20200101 ending_date should be greater than 20200601

    Args:
        url: Company url:
        query: Query of user:
        beginning_date: Start range of date for downloading dart annual report filing (YYYYMMDD):
        ending_date: Ending range of date for download dart annual report filing(YYYYMMDD):

    """
    # Returns:
    #     ToolSource: Contains summary in source_content and original documents in markdown format
    logger.info(f"Starting DART tool calling for URL: {url} with query: {query}")

    try:
        company_full_name, company_first_name, url = await _process_company_info(url)
        company_short_list = await get_dart_company_information(company_full_name, company_first_name)
        logger.info(f"Company short list: {json.dumps(company_short_list, indent=3)}")

        if company_short_list == "N/A":
            logger.info("No DART company information found.")
            return ToolSource(
                source_type="dart",
                source_content="No DART company information found for the provided URL.",
                source_path=url,
                original_documents=[]
            )

        corp_code = await _get_corp_code(company_full_name, company_short_list, url)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder_path, original_documents = await dart_search(corp_code, temp_dir, beginning_date,ending_date)
            documents = await _load_documents(folder_path)
            summary = await _generate_report(documents, query)

            return ToolSource(
                source_type="dart",
                source_content=summary,
                source_path=url,
                original_documents=original_documents
            )

    except ValueError as e:
        return ToolSource(
            source_type="dart",
            source_content=str(e),
            source_path=url,
            original_documents=[]
        )
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        logger.error(f"Unexpected error in dart_tool_calling: {e}")
        return ToolSource(
            source_type="dart",
            source_content="An unexpected error occurred while processing the request.",
            source_path=url,
            original_documents=[]
        )


async def execute_async_tool(ans):
    """Executes the appropriate asynchronous tool based on the model's tool call."""
    if ans.tool_calls:
        tool_call = ans.tool_calls[0]
        func_name = tool_call["name"]
        args = tool_call["args"]

        logger.info(f"Executing tool: {func_name} with arguments: {args}")

        if func_name == "dart_tool_calling":
            return await dart_tool_calling(**args)
    logger.warning("No tool calls found in the model's response or unknown tool.")
    return ToolSource(
        source_type="dart",
        source_content="No relevant action could be performed.",
        source_path="",
        original_documents=[]
    )


async def gather_dart_data(url: str, query: str):
    """
    Gathers DART information by invoking the LLM with available tools.
    """
    tools = [dart_tool_calling]  # dart_tool_calling is an async function and needs to be awaited
    llm = ChatOpenAI(model="gpt-4.1-nano", api_key=OPENAI_API_KEY)
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")

    # System prompt
    system_message = SystemMessage(content="""
    When using the dart_tool_calling function, ensure that:
    - beginning_date and ending_date have at least 12 monthsor 1 year difference
    - Format dates as YYYYMMDD (e.g., 20200101)
    - If beginning_date is 20200101, ending_date should be at least 20210101 or later
    - Always validate the date range before making the tool call
    """)

    # Enrich the query with the URL for the LLM
    full_query = f"Company URL: {url}\n\n{query}"
    messages = [system_message, ("human", full_query)]

    logger.info(f"Invoking LLM with query: {full_query}")
    ans = await llm_with_tools.ainvoke(messages)

    result = await execute_async_tool(ans=ans)
    logger.info(f"Final result: {result}")
    return [result]


# Utility functions for cache management
def clear_all_caches():
    """Clear all caches."""
    with cache_lock:
        dart_cache.clear()
        company_info_cache.clear()
        corp_list_cache.clear()
    logger.info("All caches cleared.")


def get_cache_info():
    """Get information about cache usage."""
    with cache_lock:
        return {
            "dart_cache": {
                "current_size": len(dart_cache),
                "max_size": dart_cache.maxsize,
                "ttl": dart_cache.ttl
            },
            "company_info_cache": {
                "current_size": len(company_info_cache),
                "max_size": company_info_cache.maxsize,
                "ttl": company_info_cache.ttl
            },
            "corp_list_cache": {
                "current_size": len(corp_list_cache),
                "max_size": corp_list_cache.maxsize,
                "ttl": corp_list_cache.ttl
            }
        }


# Example usage
if __name__ == "__main__":
    url = "https://www.woongjin.co.kr/"
    query = "Summarize financial performance metrics for woongjin in a table format, comparing recent data vs. the same period last year."

    # Show cache info before running
    print("Cache info before:", get_cache_info())

    ans = asyncio.run(gather_dart_data(url, query))
    print(ans)

    # Show cache info after running
    print("Cache info after:", get_cache_info())

    # # Run again to demonstrate caching
    # print("\n--- Running again to demonstrate caching ---")
    # ans2 = asyncio.run(gather_dart_data(url, query))
    # print("Second run completed - should be faster due to caching!")