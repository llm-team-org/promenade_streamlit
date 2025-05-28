import os
import httpx
import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Literal, Any
from dotenv import load_dotenv
import logging
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior, UserError
import json
from datetime import datetime
import tavily # Import tavily

# Load environment variables from .env file
load_dotenv()

# --- Logging Setup ---
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Dependencies ---
@dataclass
class SecApiDependencies:
    """Dataclass to hold dependencies for the agent, including API keys and clients."""
    http_client: httpx.AsyncClient
    tavily_client: tavily.AsyncTavilyClient
    sec_api_key: str = os.getenv("SEC_API_KEY")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY") # Added Tavily API Key
    sec_api_base_url: str = "https://api.sec-api.io"
    sec_api_archive_url: str = "https://archive.sec-api.io"

# --- Output & Input Models ---
class AgentSecResponse(BaseModel):
    """The final response model from the agent."""
    answer: str = Field(description="The final, comprehensive answer to the user's query based on SEC filing data, web search, or general knowledge.")
    tool_used: Optional[List[str]] = Field(None, description="List of tool functions used (e.g., 'query_sec_filings', 'web_search').") # Changed to List
    source_urls: Optional[List[str]] = Field(None, description="List of relevant SEC filing or web URLs that contributed to the answer.")
    error_message: Optional[str] = Field(None, description="Any error message if the query could not be fully answered.")

class QueryFilingsParams(BaseModel):
    """Input parameters for querying SEC filings."""
    ticker: Optional[str] = Field(None, description="Company ticker symbol, e.g., AAPL.")
    cik: Optional[str] = Field(None, description="Company CIK, e.g., 320193 (do not include leading zeros).")
    form_type: Optional[str] = Field(None, description="SEC form type, e.g., '10-K', '8-K'.")
    company_name: Optional[str] = Field(None, description="Company name, e.g., 'Apple Inc.'. Ensure exact names are quoted if they contain spaces for Lucene queries.")
    query_string: Optional[str] = Field(None, description="Advanced Lucene query string. Use for complex searches not covered by other parameters.")
    start_date: Optional[str] = Field(None, description="Start date for filtering filings (YYYY-MM-DD).")
    end_date: Optional[str] = Field(None, description="End date for filtering filings (YYYY-MM-DD).")
    from_result: int = Field(0, description="Starting position for results (pagination).")
    size: int = Field(10, ge=1, le=50, description="Number of results to return (max 50).")

class FilingInfo(BaseModel):
    """Detailed information about a single SEC filing."""
    id: str
    accession_no: str = Field(..., alias="accessionNo")
    form_type: str = Field(..., alias="formType")
    filed_at: str = Field(..., alias="filedAt")
    cik: str
    ticker: Optional[str] = None
    company_name: str = Field(..., alias="companyName")
    description: str
    link_to_html: str = Field(..., alias="linkToHtml")
    link_to_txt: str = Field(..., alias="linkToTxt")
    period_of_report: Optional[str] = Field(None, alias="periodOfReport")
    class Config: populate_by_name = True

class QueryFilingsOutput(BaseModel):
    """Output containing a list of found filings and total count."""
    filings: List[FilingInfo]
    total_value: int = Field(..., alias="value")
    total_relation: str = Field(..., alias="relation")
    class Config: populate_by_name = True

class ExtractSectionParams(BaseModel):
    """Input parameters for extracting a section from an SEC filing."""
    filing_url: str = Field(..., description="The SEC.gov URL of the filing.")
    item_code: str = Field(..., description="The item code to extract (e.g., '1A', 'part2item1a', '1-1').")
    return_type: Literal['text', 'html'] = Field('text', description="Return type: 'text' or 'html'.")

class ExtractSectionOutput(BaseModel):
    """Output containing the extracted section content."""
    section_content: Optional[str] = Field(None, description="The extracted content.")
    status: str = Field(..., description="Status of the extraction.")
    error_message: Optional[str] = Field(None, description="Error message if failed.")

# --- Added Tavily Tool Models ---
class WebSearchParams(BaseModel):
    """Input parameters for performing a web search."""
    query: str = Field(..., description="The search query for the web.")

class WebSearchOutput(BaseModel):
    """Output containing the answer and sources from a web search."""
    answer: str = Field(description="The summarized answer found from the web search.")
    source_urls: Optional[List[str]] = Field(None, description="List of source URLs from the web search.")

# --- System Prompt & Agent Initialization ---
SYSTEM_PROMPT = """You are an expert financial assistant. Your capabilities include:
1.  **SEC Filings Analysis:** Accessing and extracting data from SEC filings using `query_sec_filings` and `extract_filing_section` tools via sec-api.io. Use these tools for questions about specific company filings (10-K, 8-K, etc.), financial data, risk factors, or specific sections.
2.  **Web Search:** Searching the web for current news, general financial information, market trends, or context that isn't typically found in SEC filings using the `web_search` tool via Tavily.

**Your Strategy:**
-   **Prioritize SEC Tools:** If a question *can* be answered with SEC data, use the SEC tools first.
-   **Use Web Search:** If the question is about recent news, broad market topics, or information *not* in filings, use `web_search`.
-   **Synthesize:** If needed, combine information from both SEC filings and web searches to provide a comprehensive answer.
-   **Be Accurate:** Only provide information you can verify through your tools. If you cannot find an answer, state that clearly. Do not invent data.
-   **Cite Sources:** When using tools, include relevant source URLs (SEC filing links or web URLs) in your final response.
-   **Be Concise:** Summarize information when appropriate, focusing on the user's core question.
-   **Tool Selection:** Choose the most appropriate tool(s) based on the user's query. If you need a list of filings, use `query_sec_filings`. If you need content from a specific filing URL, use `extract_filing_section`. If you need general info or news, use `web_search`.
"""

sec_filing_agent = Agent(
    model='openai:gpt-4o-mini', # Using a generally available and capable model
    deps_type=SecApiDependencies,
    output_type=AgentSecResponse,
    system_prompt=SYSTEM_PROMPT
)

# --- Tool Implementations ---
@sec_filing_agent.tool
async def query_sec_filings(ctx: RunContext, params: QueryFilingsParams) -> QueryFilingsOutput:
    """
    Queries sec-api.io for SEC filings based on ticker, CIK, form type, company name, or a general Lucene query string.
    Useful for finding a list of filings matching specific criteria.
    """
    logging.info(f"QUERY_SEC_FILINGS: \n{params.model_dump_json(indent=2)}")
    if not ctx.deps.sec_api_key:
        raise UserError("SEC_API_KEY environment variable not set.")

    query_parts = []
    if params.ticker: query_parts.append(f"ticker:\"{params.ticker}\"")
    if params.cik: query_parts.append(f"cik:\"{params.cik}\"")
    if params.form_type: query_parts.append(f"formType:\"{params.form_type}\"")
    if params.company_name: query_parts.append(f"companyName:\"{params.company_name}\"")

    date_query_part = ""
    if params.start_date and params.end_date :
        date_query_part = f"filedAt:[{params.start_date} TO {params.end_date}]"
    elif params.start_date:
        date_query_part = f"filedAt:[{params.start_date} TO {datetime.now().strftime('%Y-%m-%d')}]"
    elif params.end_date:
        date_query_part = f"filedAt:[1970-01-01 TO {params.end_date}]"

    if date_query_part and not params.query_string:
         query_parts.append(date_query_part)
    elif date_query_part and params.query_string and "filedAt" not in params.query_string:
         query_parts.append(date_query_part)

    final_query_string = " AND ".join(query_parts)
    if params.query_string:
        if final_query_string: final_query_string = f"({final_query_string}) AND ({params.query_string})"
        else: final_query_string = params.query_string

    if not final_query_string:
        raise UserError("Query parameters must be provided for query_sec_filings tool.")

    payload = {
        "query": {"query_string": {"query": final_query_string}},
        "from": str(params.from_result),
        "size": str(params.size),
        "sort": [{"filedAt": {"order": "desc"}}]
    }
    api_url = f"{ctx.deps.sec_api_base_url}/query-api" # Corrected URL
    logging.info(f"API URL: {api_url}\nPAYLOAD: {json.dumps(payload, indent=2)}")

    try:
        response = await ctx.deps.http_client.post(api_url, json=payload, params={"token": ctx.deps.sec_api_key})
        response.raise_for_status()
        data = response.json()
        logging.info(f"API Response: {json.dumps(data, indent=2)}")
        # Handle potential empty 'total'
        total_data = data.get('total', {"value": 0, "relation": "eq"})
        return QueryFilingsOutput(filings=data.get('filings', []), **total_data)
    except httpx.HTTPStatusError as e:
        error_content = e.response.text
        raise ModelRetry(f"SEC API Error (query_sec_filings): {e.response.status_code} - {error_content}. Query: {final_query_string}")
    except ValidationError as e:
        raise UnexpectedModelBehavior(f"Data validation error (query_sec_filings response): {e.errors()}")
    except Exception as e:
        raise ModelRetry(f"Unexpected error (query_sec_filings): {str(e)}. Query: {final_query_string}")

@sec_filing_agent.tool
async def extract_filing_section(ctx: RunContext, params: ExtractSectionParams) -> ExtractSectionOutput:
    """
    Extracts a specific item/section (e.g., '1A' for Risk Factors) from a given 10-K, 10-Q, or 8-K SEC filing URL.
    Use this tool when the user asks for the content of a specific part of a known filing.
    """
    logging.info(f"EXTRACT_FILING_SECTION: \n{params.model_dump_json(indent=2)}")
    if not ctx.deps.sec_api_key:
        raise UserError("SEC_API_KEY environment variable not set.")

    api_url = f"{ctx.deps.sec_api_base_url}/extractor"
    request_params = {"url": params.filing_url, "item": params.item_code, "type": params.return_type, "token": ctx.deps.sec_api_key}
    logging.info(f"API URL: {api_url}\nREQUEST PARAMS: {json.dumps(request_params, indent=2)}")

    try:
        response = await ctx.deps.http_client.get(api_url, params=request_params, timeout=60.0) # Increased timeout

        if response.status_code == 200:
            content_type = response.headers.get("content-type", "").lower()
            text_content = response.text
            if "processing" in text_content.lower() and len(text_content) < 100:
                raise ModelRetry(f"SEC API is still processing section '{params.item_code}' for URL '{params.filing_url}'. Please try again shortly.")
            if "text" in content_type or "html" in content_type:
                return ExtractSectionOutput(section_content=text_content, status="success")
            else:
                raise UnexpectedModelBehavior(f"Extractor API returned 200 OK but with unexpected content type: {content_type}. Content: {text_content[:200]}")

        response.raise_for_status()
        return ExtractSectionOutput(section_content=None, status="error", error_message="Unknown successful response format.")

    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        if e.response.status_code in [400, 404] :
             return ExtractSectionOutput(section_content=None, status="not_found", error_message=f"Invalid request or section not found ({e.response.status_code}): {error_text}")
        raise ModelRetry(f"SEC API Error (extract_filing_section): {e.response.status_code} - {error_text}")
    except httpx.TimeoutException:
        raise ModelRetry(f"Timeout while extracting section '{params.item_code}' from '{params.filing_url}'. Please try again.")
    except Exception as e:
        raise ModelRetry(f"Unexpected error (extract_filing_section): {str(e)}")

# --- Added Tavily Web Search Tool ---
@sec_filing_agent.tool
async def web_search(ctx: RunContext, params: WebSearchParams) -> WebSearchOutput:
    """
    Performs a web search using Tavily to find general information, news, or context
    that might not be available in SEC filings. Returns a concise answer and source URLs.
    """
    logging.info(f"WEB_SEARCH: \n{params.model_dump_json(indent=2)}")

    # Ensure Tavily client is available
    if not ctx.deps.tavily_client:
        if not ctx.deps.tavily_api_key:
            raise UserError("TAVILY_API_KEY environment variable not set and client not provided.")
        # Initialize if not already done (though __post_init__ should handle it)
        ctx.deps.tavily_client = tavily.AsyncTavilyClient(api_key=ctx.deps.tavily_api_key)

    try:
        logging.info(f"Performing Tavily search for: {params.query}")
        # Use Tavily's search function, requesting an answer
        response = await ctx.deps.tavily_client.search(
            query=params.query,
            search_depth="advanced",
            include_answer=True, # Request a summarized answer
            max_results=5
        )
        logging.info(f"Tavily Response: {response}")

        answer = response.get("answer", f"Could not find a direct answer for '{params.query}'. See search results for details.")
        urls = [res.get('url') for res in response.get('results', []) if res.get('url')]

        return WebSearchOutput(answer=answer, source_urls=urls)

    except Exception as e:
        logging.error(f"Tavily API Error: {str(e)}")
        raise ModelRetry(f"Web search failed: {str(e)}")


# --- Example Usage (Async Main Function) ---
async def run_agent(query: str):
    """Initializes dependencies and runs the agent with a given query."""
    # Ensure API keys are loaded and available
    if not os.getenv("SEC_API_KEY") or not os.getenv("TAVILY_API_KEY") or not os.getenv("OPENAI_API_KEY"):
         print("Error: Please ensure SEC_API_KEY, TAVILY_API_KEY, and OPENAI_API_KEY are set in your .env file.")
         return

    async with httpx.AsyncClient() as client:
        tavily_client = tavily.AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        dependencies = SecApiDependencies(http_client=client, tavily_client=tavily_client)
        print(f"Running agent with query: '{query}'...")
        try:
            result = await sec_filing_agent.run(query, deps=dependencies)
            if isinstance(result.output, AgentSecResponse):
                return result.output.answer
                # print("\n--- Agent Response ---")
                # print(f"Answer: {result.output.answer}")
                # if result.output.tool_used:
                #     print(f"Tools Used: {', '.join(result.output.tool_used)}")
                # if result.output.source_urls:
                #     print("Sources:")
                #     for url in result.output.source_urls:
                #         print(f"- {url}")
                # if result.output.error_message:
                #     print(f"Error: {result.output.error_message}")
                # print("----------------------")
            else:
                print("\n--- Agent Response ---")
                print("Agent Response not in correct format! \n Printing response ",result.output)
        except Exception as e:
            logging.error(f"Agent execution failed: {e}", exc_info=True)
            print(f"An error occurred during agent execution: {e}")

# Example queries to test the agent
# async def main():
    # Query 1: Requires SEC filing search
    # await run_agent("Find the latest 10-K filing for Apple Inc.")

    # Query 2: Requires SEC filing extraction (Needs a URL first, might need Query 1)
    # await run_agent("What are the risk factors mentioned in Apple's latest 10-K? You might need to find the 10-K first.")
    # A more direct approach if URL is known:
    # await run_agent("Extract Item 1A from https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm")

    # Query 3: Requires Web Search
    # await run_agent("What is the current market sentiment towards NVIDIA stock?")

    # Query 4: Requires both (potentially)
    # await run_agent("Summarize Tesla's recent performance based on their latest 10-Q and any recent news.")


# if __name__ == "__main__":
    # Ensure you have a .env file with OPENAI_API_KEY, SEC_API_KEY, TAVILY_API_KEY
    # asyncio.run(main())