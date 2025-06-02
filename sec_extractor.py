import requests
from pydantic import BaseModel, Field
from typing import Literal, Optional
import os

def sec_section_extractor(
    url: str,
    item: str,
) -> str:
    """
    Extracts a specific text or HTML section from an SEC 10-K, 10-Q, or 8-K filing.

    This tool interfaces with the sec-api.io Extractor API to fetch cleaned and
    standardized content from SEC filings. It supports all filings since 1994,
    including amended versions and various form types Use this to fetch real time 
    information to answer user queries.

    Supported 10-K Section Items:
        '1': Business - Overview of the company's operations and business.
        '1A': Risk Factors - Key risks facing the company.
        '1B': Unresolved Staff Comments - Outstanding comments from SEC staff.
        '1C': Cybersecurity - Cybersecurity risk management and strategy.
        '2': Properties - Information about significant properties owned or leased.
        '3': Legal Proceedings - Details on material legal actions.
        '4': Mine Safety Disclosures - Disclosures related to mine safety.
        '5': Market for Registrant’s Common Equity, Related Stockholder Matters and Issuer Purchases of Equity Securities.
        '6': Selected Financial Data (Available for filings prior to February 2021).
        '7': Management’s Discussion and Analysis of Financial Condition and Results of Operations (MD&A).
        '7A': Quantitative and Qualitative Disclosures about Market Risk.
        '8': Financial Statements and Supplementary Data.
        '9': Changes in and Disagreements with Accountants on Accounting and Financial Disclosure.
        '9A': Controls and Procedures.
        '9B': Other Information.
        '10': Directors, Executive Officers and Corporate Governance.
        '11': Executive Compensation.
        '12': Security Ownership of Certain Beneficial Owners and Management.
        '13': Certain Relationships and Related Transactions, and Director Independence.
        '14': Principal Accountant Fees and Services.
        '15': Exhibits and Financial Statement Schedules.

    Supported 10-Q Section Items:
        'part1item1': Financial Statements (Part 1).
        'part1item2': Management’s Discussion and Analysis (MD&A) (Part 1).
        'part1item3': Quantitative and Qualitative Disclosures About Market Risk (Part 1).
        'part1item4': Controls and Procedures (Part 1).
        'part2item1': Legal Proceedings (Part 2).
        'part2item1a': Risk Factors (Part 2).
        'part2item2': Unregistered Sales of Equity Securities and Use of Proceeds (Part 2).
        'part2item3': Defaults Upon Senior Securities (Part 2).
        'part2item4': Mine Safety Disclosures (Part 2).
        'part2item5': Other Information (Part 2).
        'part2item6': Exhibits (Part 2).

    Supported 8-K Section Items (Item Code format: 'Section-Item'):
        '1-1': Entry into a Material Definitive Agreement.
        '1-2': Termination of a Material Definitive Agreement.
        '1-3': Bankruptcy or Receivership.
        '1-4': Mine Safety - Reporting of Shutdowns.
        '1-5': Material Cybersecurity Incidents.
        '2-1': Completion of Acquisition or Disposition of Assets.
        '2-2': Results of Operations and Financial Condition.
        '2-3': Creation of a Direct Financial Obligation.
        '2-4': Triggering Events That Accelerate/Increase a Direct Financial Obligation.
        '2-5': Cost Associated with Exit or Disposal Activities.
        '2-6': Material Impairments.
        '3-1': Notice of Delisting or Failure to Satisfy Listing Rule.
        '3-2': Unregistered Sales of Equity Securities.
        '3-3': Material Modifications to Rights of Security Holders.
        '4-1': Changes in Registrant's Certifying Accountant.
        '4-2': Non-Reliance on Previously Issued Financial Statements.
        '5-1': Changes in Control of Registrant.
        '5-2': Departure/Election of Directors; Appointment/Compensation of Officers.
        '5-3': Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year.
        '5-4': Temporary Suspension of Trading Under Employee Benefit Plans.
        '5-5': Amendments to Code of Ethics.
        '5-6': Change in Shell Company Status.
        '5-7': Submission of Matters to a Vote of Security Holders.
        '5-8': Shareholder Nominations.
        '6-1': ABS Informational and Computational Material.
        '6-2': Change of Servicer or Trustee.
        '6-3': Change in Credit Enhancement.
        '6-4': Failure to Make a Required Distribution.
        '6-5': Securities Act Updating Disclosure.
        '6-6': Static Pool.
        '6-10': Alternative Filings of Asset-Backed Issuers.
        '7-1': Regulation FD Disclosure.
        '8-1': Other Events.
        '9-1': Financial Statements and Exhibits.
        'signature': Signature section.

    Args:
        url: The URL of the SEC filing.
        item: The specific item code to extract.
        token: Your sec-api.io API key.
        return_type: The desired format, 'text' or 'html'.

    Returns:
        An extracted content from the api.
    """
    API_ENDPOINT = "https://api.sec-api.io/extractor"
    params = {
        'url': url,
        'item': item,
        'type': 'text',
        'token': os.getenv("SEC_API_KEY")
    }

    try:
        response = requests.get(API_ENDPOINT, params=params)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        # Handle potential network errors or bad responses
        return f"An error occurred: {e}"

# Example Usage (requires a valid API token):
#
# from_api_key = "YOUR_API_KEY" # Replace with your actual key
# filing_url = "https://www.sec.gov/Archives/edgar/data/1318605/000156459021004599/tsla-10k_20201231.htm"
#
# # Extract Risk Factors (1A) as text
# input_data = SecExtractorInput(url=filing_url, item="1A", token=from_api_key, return_type="text")
# output = sec_section_extractor(
#     url=input_data.url,
#     item=input_data.item,
#     token=input_data.token,
#     return_type=input_data.return_type
# )
# print(output.extracted_content[:500] + "...") # Print first 500 characters