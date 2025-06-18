import requests
import json
from typing import List, Dict, Optional, Union
import os

def query_sec_filings(
    query: str,
    from_index: int = 0,
    size: int = 10,
    sort: Optional[List[Dict[str, Dict[str, str]]]] = None,
) -> Dict:
    """
    Searches and filters SEC EDGAR filings using the Query API.

    This tool allows searching and filtering over 18+ million filings and exhibits
    published on the SEC EDGAR database since 1993 to present. New filings are added
    in 300 milliseconds after their publication on EDGAR. The API accepts simple
    and complex search expressions and returns the metadata of matching EDGAR filings
    in JSON format.

    The EDGAR filings are searchable by numerous parameters, such as:
    - CIK (Central Index Key)
    - Ticker symbol or name of the filer
    - Form type
    - Filing date (filedAt)
    - Accession number
    - Item IDs (for Form 8-K or Form 1-U filings)
    - Exhibit types (documentFormatFiles.type)
    - Series and class/contract IDs (seriesAndClassesContractsInformation.series,
      seriesAndClassesContractsInformation.classesContracts.classContract)
    - Filer entity properties like SIC (entities.sic), state of incorporation
      (entities.stateOfIncorporation), IRS number (entities.irsNo), and file number
      (entities.fileNo).
    - Period of Report (periodOfReport)
    - Effectiveness Date (effectivenessDate)
    - Effectiveness Time (effectivenessTime)
    - Registration Form (registrationForm)
    - Reference Accession Number (referenceAccessionNo)
    - Group Members (groupMembers)

    The `query` parameter uses Lucene syntax (field:value) and supports logical operators
    (AND, OR, NOT) and nested field searches. The maximum length of the query string
    cannot exceed 3500 characters.

    To paginate through results, use the `from_index` parameter to specify the
    starting position. The `size` parameter determines the number of filings returned
    per request (max 50). If more than 10,000 filings match a query, it is
    recommended to refine the search using date range filters (e.g., month by month,
    year over year) and then paginate through those smaller sets.

    The default sorting order is descending by 'filedAt' datetime field (most recent filing first).
    This can be overridden using the `sort` parameter.

    Authentication is done via an API key, which can be provided either in the
    'Authorization' header or as a 'token' query parameter. This function uses
    the 'Authorization' header method by default.

    Args:
        query (str): The search criteria in Lucene syntax. Examples:
            - 'formType:"10-K"'
            - 'ticker:AAPL AND formType:"10-K"'
            - 'cik:(12345, 67890)'
            - 'companyName:"MICROSOFT CORP"'
            - 'filedAt:[2022-01-01 TO 2022-12-31]'
            - 'items:"2.02" AND formType:"8-K"'
            - 'documentFormatFiles.type:"EX-21" AND formType:"10-K"'
            - 'formType:EFFECT AND registrationForm:"S-3"'
            - 'id:*' (to match all filings)
            For CIKs, remove leading zeros (e.g., '0000320193' becomes '320193').
            Ticker symbols are case-insensitive. Company names with spaces should be
            enclosed in double quotes.
        from_index (int, optional): The starting position of your search results,
            facilitating pagination. Default is 0. Maximum allowed value is 10,000.
        size (int, optional): Determines the number of filings returned per request.
            Default is 50. Maximum allowed value is 50.
        sort (List[Dict[str, Dict[str, str]]], optional): An array of objects
            that specify how the returned filings are sorted. Default is
            `[{ "filedAt": { "order": "desc" }}]`. Example:
            `[{ "periodOfReport": { "order": "asc" }}]`


    RETURNS
    The Query API returns a JSON object containing metadata about matching SEC filings. This object has two main fields:

    * `total` (object): Provides information about the total number of filings matching the query.
        * `value` (number): The total count of filings. This value is capped at 10,000; if more than 10,000 filings match, `value` will be 10,000, and `relation` will be "gte".
        * `relation` (string): Indicates the relationship of `value` to the actual total. "eq" means equal, "gte" means greater than or equal to.
    * `filings` (array of objects): A list of up to 50 filing objects, each containing detailed metadata about a specific SEC filing. Each filing object includes the following fields:
        * `id` (string): A unique system-internal ID for the filing object. Multiple filing objects can share the same `accessionNo` if a filing references multiple entities.
        * `accessionNo` (string): The EDGAR accession number of the filing (e.g., "0000028917-20-000033").
        * `formType` (string): The EDGAR filing form type (e.g., "10-K", "4", "8-K/A").
        * `filedAt` (string): The date and time the filing was accepted by EDGAR, in ISO 8601 format (e.g., "2019-12-06T14:41:26-05:00"). The timezone is always Eastern Time (ET).
        * `cik` (string): The CIK (Central Index Key) of the filing issuer, with leading zeros removed.
        * `ticker` (string, optional): The ticker symbol of the filing company. Not available for non-publicly traded companies.
        * `companyName` (string): The name of the primary filing company or person.
        * `companyNameLong` (string): The longer version of the company name, including filer type (e.g., "ALLIED MOTION TECHNOLOGIES INC (0000046129) (Issuer)").
        * `description` (string): A description of the form, potentially including item numbers reported (e.g., "Form 10-Q - Quarterly report [Sections 13 or 15(d)]" or "Form 8-K - Current report - Item 1.03 Item 3.03 Item 5.02 Item 9.01").
        * `linkToFilingDetails` (string): The URL to the actual filing content on sec.gov.
        * `linkToTxt` (string): The URL to the plain text (.TXT) version of the filing, which can be very large.
        * `linkToHtml` (string): The URL to the index page (filing detail page) of the filing.
        * `periodOfReport` (string, optional): The period of report in YYYY-MM-DD format (e.g., "2021-06-08"). Its meaning varies by form type (e.g., fiscal year end for 10-K, transaction date for Form 4).
        * `effectivenessDate` (string, optional): The effectiveness date in YYYY-MM-DD format, reported on certain form types like EFFECT.
        * `effectivenessTime` (string, optional): The effectiveness time in HH:mm:ss format, only reported for EFFECT forms.
        * `registrationForm` (string, optional): The registration form type as reported on EFFECT forms (e.g., "S-1").
        * `referenceAccessionNo` (string, optional): A reference accession number as reported on EFFECT forms.
        * `items` (array of strings, optional): An array of item strings reported on specific forms (e.g., 8-K, D, ABS-15G, 1-U).
        * `groupMembers` (array of strings, optional): An array of member strings reported on SC 13G and SC 13D filings.
        * `entities` (array of objects): A list of all entities referenced in the filing. The first entity in the array is always the filing issuer. Each entity object contains:
            * `companyName` (string): The company name of the entity.
            * `cik` (string): The CIK of the entity, including leading zeros.
            * `irsNo` (string, optional): The IRS number of the entity.
            * `stateOfIncorporation` (string, optional): The state of incorporation of the entity.
            * `fiscalYearEnd` (string, optional): The fiscal year end of the entity (e.g., "0930").
            * `sic` (string, optional): The SIC (Standard Industrial Classification) code of the entity.
            * `type` (string, optional): The type of filing being filed, same as `formType`.
            * `act` (string, optional): The SEC act under which the filing was filed (e.g., "34").
            * `fileNo` (string, optional): The filer number of the entity.
            * `filmNo` (string, optional): The film number of the entity.
        * `documentFormatFiles` (array of objects): An array listing all primary files of the filing, including exhibits. The first item is the filing itself, the last is the .TXT version, and others are exhibits or other documents. Each object includes:
            * `sequence` (string, optional): The sequence number of the file.
            * `description` (string, optional): A description of the file (e.g., "EXHIBIT 31.1").
            * `documentUrl` (string): The URL to the file on SEC.gov.
            * `type` (string, optional): The type of the file (e.g., "EX-31.1", "GRAPHIC").
            * `size` (string, optional): The size of the file in bytes.
        * `dataFiles` (array of objects): A list of data files, primarily for XBRL filings. Each object includes:
            * `sequence` (string): The sequence number of the file.
            * `description` (string): A description of the file (e.g., "XBRL INSTANCE DOCUMENT").
            * `documentUrl` (string): The URL to the file on SEC.gov.
            * `type` (string, optional): The type of the file (e.g., "EX-101.INS").
            * `size` (string, optional): The size of the file in bytes.
        * `seriesAndClassesContractsInformation` (array of objects, optional): List of series and classes/contracts information. Each object includes:
            * `series` (string): Series ID.
            * `name` (string): Name of the entity.
            * `classesContracts` (array of objects): List of classes/contracts. Each object includes:
                * `classContract` (string): Class/Contract ID.
                * `name` (string): Name of class/contract.
                * `ticker` (string): Ticker of the class/contract.

    Returns:
        Dict: A dictionary containing the API response. The response includes:
            - 'total' (Dict): An object with 'value' (total number of matching filings, capped at 10,000)
              and 'relation' (e.g., "gte" if value is capped).
            - 'filings' (List[Dict]): A list of filing metadata objects, each containing
              fields like 'id', 'accessionNo', 'formType', 'filedAt', 'cik', 'ticker',
              'companyName', 'linkToFilingDetails', 'entities', 'documentFormatFiles',
              'dataFiles', 'seriesAndClassesContractsInformation', and more.
              Refer to the API documentation for the full list of fields in the filing objects.
            Returns an error dictionary if the request fails.
    """
    url = "https://api.sec-api.io"
    headers = {
        "Content-Type": "application/json",
        "Authorization": os.getenv("SEC_API_KEY")
    }

    payload = {
        "query": query,
        "from": str(from_index),
        "size": str(size)
    }
    if sort:
        payload["sort"] = sort

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e), "status_code": getattr(e.response, "status_code", None)}