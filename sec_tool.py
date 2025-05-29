from sec_extractor import sec_section_extractor
from sec_filings_query import query_sec_filings
from sec_full_text_search import sec_full_text_search
from google.genai import types, Client
from dotenv import load_dotenv
load_dotenv()

def sec_tool_function(query: str) -> str:
    """SEC Filings Search Tool. Use it to find answer to queries based on SEC Filings Document

    Args:
        query (str): Query for which you want answer from SEC Filings Documents

    Returns:
        str: Answer to query based on SEC Filings Documents
    """
    client = Client()

    config = types.GenerateContentConfig(
        tools=[sec_section_extractor, sec_full_text_search],
        system_instruction="""Your primary task is to answer the user's question by querying SEC filings.
    **Workflow:**
    1.  **Identify Filing URLs:** Begin by using the `sec_full_text_search` tool to identify and retrieve the URLs of relevant SEC filings. This tool is designed to provide the initial access point to the filing data.
    2.  **Extract Sectional Information:** Once the filing URLs are obtained, leverage the `sec_section_extractor` tool. This tool will allow you to pinpoint and extract specific sections or information within those filings to formulate your answer.
    **Important:** Strictly adhere to using `sec_full_text_search` for URL discovery and `sec_section_extractor` for content extraction within filings.""")  # Pass the function itself

    # Make the request
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=query,
        config=config,
    )

    return response.text