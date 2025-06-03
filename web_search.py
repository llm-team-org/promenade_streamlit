from tavily import TavilyClient
import os

def web_search_tool(query:str) -> str:
    """Web-Search Tool. Use it to find answer to queries from the Internet

    Args:
        query (str): Query for which you want answers to from the web

    Returns:
        str: Answer to query based on web search results
    """
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    response = client.search(query=query, include_answer=True)

    return response.get('answer')

