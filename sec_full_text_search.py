import requests
import json
from typing import List, Dict, Optional, Union
import os

def sec_full_text_search(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    # ciks: Optional[List[str]] = None,
    form_types: Optional[List[str]] = None,
    # page: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Performs a full-text search across SEC EDGAR filings and exhibits
    submitted since 2001 using the sec-api.io Full-Text Search API.
    Use this tool to get real time information about sec-filings-url and anyother 
    information in the filings array.

    ## Args
    ### Parameters

    -   query (string, required)
        
        Defines the case-insensitive search term or phrase used to search the content of filings and their attachments. This can be a single word, phrase, or combination of words and phrases.
        
        -   **Single term matching:** `apple` returns all filings and attachments mentioning "apple".
        -   **Exact phrase matching:** Enclose a phrase in quotation marks to search for it in the specified order. Example: `"Fiduciary Product"` will retrieve documents containing the exact phrase "Fiduciary Product" in that order.
        -   **Wildcard searches:** Append a `*` to a keyword to search for variations of that word (e.g., stem words). Wildcards cannot be used at the beginning or middle of a word, nor within exact phrase matches. Example: `gas*` finds documents containing terms like gas or gasoline.
        -   **Boolean OR:** Use `OR` (capitalized) between terms or phrases to specify that at least one of the terms must appear in the document. By default, all search words and phrases are required unless separated by `OR`. Example: `Gasoline "Sacramento CA" OR "San Francisco CA"` retrieves documents containing gasoline and either Sacramento CA or San Francisco CA.
        -   **Exclusions:** Use a hyphen (`-`) or the capitalized `NOT` keyword immediately before a term to exclude it from search results. Example: `software -hardware` finds documents containing software but excludes any that also contain hardware.
    -   startDate (string, optional)
        
        Specifies the start date of a date range search, denoting the beginning of the range. Used in combination with endDate to find filings and exhibits filed between the two dates.
        
        -   **Format:** `YYYY-mm-dd`
        -   **Example:** `2021-02-19`
        -   **Default:** 30 days ago.
    -   endDate (string, optional)
        
        Specifies the end date of the date range search.
        
        -   **Format:** `YYYY-mm-dd`
        -   **Example:** `2021-02-19`
        -   **Default:** today.
    -   ciks (array of strings, optional)
        
        Restricts search to filings from specific CIKs. Leading zeros are optional but may be included.
        
        -   **Example:** `[ "0001811414", "1318605" ]`
        -   **Default:** all CIKs.
    -   formTypes (array of strings, optional)
        
        Search specific EDGAR form types. If defined, only filings of the specified form types are considered. All other filing types are ignored.
        
        -   **Example:** `[ "8-K", "10-Q", "10-K" ]`
        -   **Default:** all form types.

    ## Returns
    ### Filings Array

    The `filings` array contains objects, each representing a filing or exhibit. Each object has the following properties:

    -   **`accessionNo`** (string): The accession number of the filing.
        -   Example: `0000065011-21-000020`
    -   **`cik`** (string): The CIK (Central Index Key) of the filer, with leading zeros removed.
        -   Example: `65011`
    -   **`companyNameLong`** (string): The full name of the filing company.
        -   Example: `MEREDITH CORP (MDP) (CIK 0000065011)`
    -   **`ticker`** (string): The ticker symbol of the filer, if available.
    -   **`description`** (string): A description of the document.
        -   Example: `EXHIBIT 99 FY21 Q2 EARNINGS PRESS RELEASE`
    -   **`formType`** (string): The EDGAR filing type.
        -   Example: `8-K`
    -   **`type`** (string): The document type.
        -   Example: `EX-99`
    -   **`filingUrl`** (string): The URL to the filing or attachment.
        -   Example: `https://www.sec.gov/Archives/edgar/data/65011/000006501121000020/fy21q2exh99earnings.htm`
    -   **`filedAt`** (string): The filing date in `YYYY-mm-dd` format.
        -   Example: `2021-02-04`
    """

    ciks = None
    page = None

    api_endpoint = "https://api.sec-api.io/full-text-search"
    params = {"token": os.getenv("SEC_API_KEY")}

    payload = {"query": query}

    if start_date:
        payload["startDate"] = start_date
    if end_date:
        payload["endDate"] = end_date
    if ciks:
        payload["ciks"] = ciks
    if form_types:
        payload["formTypes"] = form_types
    if page:
        payload["page"] = page

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            api_endpoint,
            params=params,
            json=payload,
            headers=headers
            )
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the API request: {e}")
        # Optionally, return a specific error structure or raise the exception
        return {"error": str(e), "total": {"value": 0, "relation": "eq"}, "filings": []}
    except json.JSONDecodeError:
        print("Failed to decode JSON response.")
        return {"error": "Invalid JSON response", "total": {"value": 0, "relation": "eq"}, "filings": []}

# Example Usage (replace 'YOUR_API_KEY' with your actual key)
# api_key = "YOUR_API_KEY"
# search_query = "\"substantial doubt\""
# start = "2024-01-01"
# end = "2024-03-31"
# forms = ["10-K"]

# results = sec_full_text_search(
#     api_key=api_key,
#     query=search_query,
#     start_date=start,
#     end_date=end,
#     form_types=forms
# )

# print(json.dumps(results, indent=4))