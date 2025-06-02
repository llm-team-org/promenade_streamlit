from sec_extractor import sec_section_extractor
from sec_filings_query import query_sec_filings
from sec_full_text_search import sec_full_text_search
from google.genai import types, Client
from dotenv import load_dotenv
load_dotenv()

def sec_tool_function(query: str) -> str:
    """Use the SEC Filings Search Tool to extract specific text or HTML sections from SEC 10-K, 10-Q, or 8-K filings. This tool is designed to provide you real time information of SEC Filings data to answer user queries. It's useful for retrieving cleaned and standardized content from public company disclosures since 1994, including amended versions.

    You can use this tool to find various types of information, such as:

    * **Company Operations and Business:** Ask about a company's core business, products, services, and operational strategies.
    * **Company Risks:** Inquire about potential risks and uncertainties that could affect a company's performance.
    * **Financial Performance and Condition:** Request details on revenue, expenses, profits, cash flow, assets, liabilities, and overall financial health. This includes questions about annual revenue, quarterly earnings, and financial trends.
    * **Legal Issues:** Seek information regarding any material legal proceedings or disputes involving the company.
    * **Executive and Director Information:** Get details about executive compensation, board members, and corporate governance practices.
    * **Changes in Company Structure:** Ask about significant corporate events like mergers, acquisitions, changes in accounting methods, or shifts in control.
    * **Cybersecurity Posture:** Inquire about a company's cybersecurity risk management and incident disclosures.
    * **Other Material Events:** Find information on any other significant events that a company is required to disclose.

    **Examples of natural language queries this tool can handle:**

    * "What was Apple's annual revenue for 2023?" (The tool will infer it needs to look in financial statements or MD&A of a 10-K.)
    * "Describe the risk factors for Microsoft's cloud computing business." (The tool will look in the Risk Factors section of a 10-K or 10-Q.)
    * "What are the significant legal proceedings involving Tesla?" (The tool will look in the Legal Proceedings section of a 10-K or 10-Q.)
    * "Summarize the executive compensation for Google's CEO in their latest 10-K." (The tool will look in the Executive Compensation section of a 10-K.)
    * "Has Amazon disclosed any material cybersecurity incidents recently?" (The tool will look in the relevant 8-K or 10-K sections.)

    Args:
        query (str): A detailed natural language query describing the specific information you need from an SEC filing. The tool will use this query to identify the most relevant filing type (10-K, 10-Q, or 8-K) and the specific section item within that filing to extract the answer.

    Returns:
        str: The answer to the query provided to the tool based on information in the SEC filings documents.
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
        model="gemini-1.5-flash",
        contents=query,
        config=config,
    )

    return response