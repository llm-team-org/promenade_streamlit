import streamlit as st
from prom_functions import (
    generate_company_information,
    generate_corp_code,
    short_list,
    sec_search,
    sec_get_report,
    dart_search,
    dart_get_report
)
import asyncio
import os
import nest_asyncio
import tempfile

# Apply nest_asyncio to handle asyncio in Streamlit (as in original)
# This should be called once at the beginning.
nest_asyncio.apply()

# Configure Streamlit page
st.set_page_config(
    page_title="IM Draft Generator",
    page_icon="📊",
    layout="wide"
)

if 'report_list' not in st.session_state:
    st.session_state.report_list = []

if 'report_to_display' not in st.session_state:
    st.session_state.report_to_display = None

st.title("📊IM Draft Generator")
st.markdown("Generate comprehensive investment reports for companies using SEC or DART filings")

# Sidebar for inputs
st.sidebar.header("Configuration")

# Language selection
filings = st.sidebar.selectbox(
    "Select filings:",
    ["Global SEC filings", "Korean Dart fillings"],
    index=0
)

if filings == "Global SEC filings":
    language = "english"
else:
    language = "korean"

# Company URL input
company_url = st.sidebar.text_input(
    "Enter Company URL:",
    placeholder="https://example.com"
)

# Generate report button
generate_button = st.sidebar.button("🚀 Generate Report", type="primary")

if st.session_state.report_to_display:
    report_to_display_state = None
    st.sidebar.button(
        "View Instructions",
        on_click=lambda: setattr(st.session_state, 'report_to_display', None)
    )

# Display button for each report in st.session_state.report_list which when clicked will set the report_to_display variable to the report
if not st.session_state.report_list:
    st.sidebar.write("No reports found.")
else:
    st.sidebar.header("Report List")


def set_report_to_display(report):
    st.session_state.report_to_display = report


# Fixed section with unique keys
for i, report_data in enumerate(st.session_state.report_list):
    col1, col2 = st.sidebar.columns(2)
    col1.button(
        f"{report_data['url']}-{report_data['language']}",
        on_click=set_report_to_display,
        args=(report_data,),
        key=f"view_report_{i}"  # Unique key for each view button
    )
    col2.button(
        "❌",
        on_click=lambda report=report_data: st.session_state.report_list.remove(report),
        key=f"delete_report_{i}"  # Unique key for each delete button
    )


def display_report(report_data):
    company_data = report_data.get('company_data', {})
    if not company_data or "error" in company_data:
        st.error(f"❌ Failed to extract company information: {company_data.get('error', 'Unknown error')}")
        if "raw_content" in company_data: st.expander("Raw LLM Output").write(company_data["raw_content"])
        return

    st.success("✅ Company information extracted successfully!")

    # Display company data
    st.subheader("📋 Company Information")
    with st.expander("View Company Details", expanded=True):
        st.json(company_data)

    # Extract key information
    full_name = company_data.get('company_name', 'N/A')
    first_name = company_data.get('company_first_name', 'N/A')
    ticker = company_data.get('ticker', 'N/A')

    if full_name == 'N/A':
        st.error("❌ Company name could not be determined. Cannot proceed.")
        return

    # Display basic info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Company Name", full_name)
    with col2:
        st.metric("First Name", first_name)
    with col3:
        st.metric("Ticker", ticker)

    st.markdown("---")
    report = report_data.get('report', '')
    images = report_data.get('images', [])
    selected_language = report_data.get('language', '')

    # Process based on language
    if selected_language.lower() == "english":
        st.subheader("🇺🇸 SEC Filing Analysis")

        filings_data = report_data.get('filings_data', {})

        if not filings_data or not filings_data.get('filings'):
            st.warning("⚠️ No SEC filings found or error in fetching.")
        else:
            st.success(f"✅ Found {len(filings_data.get('filings', []))} SEC filings.")
            with st.expander("View SEC Filings", expanded=False):
                st.json(filings_data)

            urls = [filing['filingUrl'] for filing in filings_data['filings'] if 'filingUrl' in filing]
            if not urls:
                st.warning("⚠️ No URLs found in SEC filings to generate report from.")
            else:
                with st.spinner("📊 Generating comprehensive SEC report..."):
                    report = report_data.get('report', '')
                    images = report_data.get('images', [])
                st.success("✅ SEC report generated successfully!")

    elif selected_language.lower() == "korean":
        st.subheader("🇰🇷 DART Filing Analysis")

        corp_short_list_data = report_data.get('corp_short_list_data', {})
        report_source = report_data.get('report_source', 'web')
        web_search_reason = report_data.get('web_search_reason', '')

        if isinstance(corp_short_list_data, str) and "not in the dart list" in corp_short_list_data.lower():
            st.info("ℹ️ Company not in DART list. Report generated using web search.")
        elif web_search_reason == "not in short dart list":
            st.info("ℹ️ Company in DART list but not found in short DART list. Report generated using web search.")
        elif web_search_reason == "error in dart lookup":
            st.info("ℹ️ Error in DART lookup. Report generated using web search.")
        elif web_search_reason == "corp code generation failed":
            st.info("ℹ️ DART corporation code generation failed. Report generated using web search.")
        elif not corp_short_list_data:
            st.info("ℹ️ Company not found in DART list. Report generated using web search.")
        else:
            st.success("✅ Company found in DART short list.")
            with st.expander("View Short List", expanded=False):
                st.write(corp_short_list_data)

            corp_code_data = report_data.get('corp_code_data', {})
            if corp_code_data and "error" not in corp_code_data and corp_code_data.get('corp_code') != 'N/A':
                st.success("✅ DART Corporation code generated.")
                with st.expander("View Corporation Code", expanded=False):
                    st.json(corp_code_data)

        if report_source == 'web':
            st.info("ℹ️ Report generated using web search.")
        else:
            st.success("✅ Success! Report generated using DART filings!")

    if report_data.get('logs'):
        with st.expander("📊 Research Logs"):
            st.write(report_data['logs'])

    # Display report with download button
    if report:
        st.subheader(f"📈 {selected_language.capitalize()} Investment Report")

        # Add download button before the report display
        col1, col2 = st.columns([1, 4])
        with col1:
            # Create filename based on company name and language
            company_name_clean = full_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename = f"{company_name_clean}_{selected_language}_report.md"

            st.download_button(
                label="📥 Download Report",
                data=report,
                file_name=filename,
                mime="text/markdown",
                type="primary"
            )

        with st.expander("View Full Report", expanded=True):
            st.markdown(report)
    elif not (
            "Error" in report if isinstance(report, str) else False):  # Only show if no error message already in report
        st.info("ℹ️ Report generation did not produce output, or path was skipped.")

    # Display images if any
    if images:
        st.subheader("🖼️ Report Images")
        for i, image_data in enumerate(images):
            # Assuming image_data could be URL, path, or bytes. St.image handles these.
            st.image(image_data, caption=f"Report Image {i + 1}")


# Main async function to handle the report generation flow
async def generate_report_flow(company_url_input, selected_language):
    report_data = {'url': company_url_input, 'language': selected_language}
    # Step 1: Generate company information
    with st.spinner("🔍 Analyzing company information..."):
        company_data = await generate_company_information(company_url_input, selected_language)
        report_data['company_data'] = company_data

    if not company_data or "error" in company_data:
        st.error(f"❌ Failed to extract company information: {company_data.get('error', 'Unknown error')}")
        if "raw_content" in company_data: st.expander("Raw LLM Output").write(company_data["raw_content"])
        return

    st.success("✅ Company information extracted successfully!")

    # Display company data
    st.subheader("📋 Company Information")
    with st.expander("View Company Details", expanded=True):
        st.json(company_data)

    # Extract key information
    full_name = company_data.get('company_name', 'N/A')
    first_name = company_data.get('company_first_name', 'N/A')
    ticker = company_data.get('ticker', 'N/A')

    if full_name == 'N/A':
        st.error("❌ Company name could not be determined. Cannot proceed.")
        return

    # Display basic info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Company Name", full_name)
    with col2:
        st.metric("First Name", first_name)
    with col3:
        st.metric("Ticker", ticker)

    # Query template
    query_template = f"""As an investment associate, draft an information memorandum for company: {full_name}
    Information of Company: {company_data}
    ADD These in table of contents:

    These are the Headings you need to use for IM and then generate sub headings for each heading
    1.Executive Summary
    2.Investment Highlights
    3.Company Overview
        Introduction to {full_name}
        History, Mission, and Core Values
        Global Presence and Operations
    4.Business Model, Strategy, and Product
    5.Business Segments Deep Dive
    6.Industry Overview and Competitive Positioning
    7.Financial Performance Analysis
    8.Management and Corporate Governance
    9.Strategic Initiatives and Future Growth Drivers
    10.Risk Factors
    11.Investment Considerations
    12.Conclusion
    13.References
    """
    st.markdown("---")
    report = ""
    images = []

    # Process based on language
    if selected_language.lower() == "english":
        st.subheader("🇺🇸 SEC Filing Analysis")

        with st.spinner("📄 Searching SEC filings..."):
            filings_data = await sec_search(full_name)  # Use full_name or ticker if more appropriate
            report_data['filings_data'] = filings_data

        if not filings_data or not filings_data.get('filings'):
            st.info("⚠️ No SEC filings found or error in fetching.")
            urls = []
        else:
            st.success(f"✅ Found {len(filings_data.get('filings', []))} SEC filings.")
            with st.expander("View SEC Filings", expanded=False):
                st.json(filings_data)

            urls = [filing['filingUrl'] for filing in filings_data['filings'] if 'filingUrl' in filing]
            if not urls:
                st.warning("⚠️ No URLs found in SEC filings to generate report from.")
            # else:
            #     with st.expander('📊 Research Logs', expanded=True):
            #         logs_container = st.empty()  # Create a placeholder for logs
            #         logs_container.info("Logs will appear here as the research progresses...")
            #     reports_container = st.empty()  # Create a placeholder for reports
            #     reports_container.info("The final report will be displayed here once generated.")
        with st.expander('📊 Research Logs', expanded=True):
            logs_container = st.empty()  # Create a placeholder for logs
            logs_container.info("Logs will appear here as the research progresses...")
        reports_container = st.empty()  # Create a placeholder for reports
        reports_container.info("The final report will be displayed here once generated.")
        report, images, logs = await sec_get_report(query=query_template, report_type="research_report",
                                                    sources=urls[:2], logs_container=logs_container,
                                                    report_container=reports_container)
        report_data['report'] = report
        report_data['images'] = images
        report_data['logs'] = logs
        st.success("✅ SEC report generated successfully!")

    elif selected_language.lower() == "korean":
        st.subheader("🇰🇷 DART Filing Analysis")

        with st.spinner("📝 Generating company short list for DART..."):
            # Ensure first_name is available, or use a placeholder/fallback
            company_first_name_for_dart = first_name if first_name != 'N/A' else full_name.split(" ")[0]
            corp_short_list_data = await short_list(full_name, company_first_name_for_dart)
            report_data['corp_short_list_data'] = corp_short_list_data

        use_web_search = False
        web_search_reason = ""

        # Check if company is not in corp list at all
        if isinstance(corp_short_list_data, str) and "not in the dart list" in corp_short_list_data.lower():
            st.info("ℹ️ Company not in DART list. Using web search instead.")
            use_web_search = True
            web_search_reason = "not in dart list"
        # Check if there's an error in the corp list lookup
        elif isinstance(corp_short_list_data, str) and "Error" in corp_short_list_data:
            st.info(f"ℹ️ Error in DART lookup: {corp_short_list_data}. Using web search instead.")
            use_web_search = True
            web_search_reason = "error in dart lookup"
        # Check if company is in corp list but not found in short list
        elif not corp_short_list_data or (isinstance(corp_short_list_data, dict) and not corp_short_list_data):
            st.info("ℹ️ Company in DART list but not found in short DART list. Using web search instead.")
            use_web_search = True
            web_search_reason = "not in short dart list"
        # Company found in both corp list and short list - proceed with DART filing download
        else:
            st.success("✅ Company found in DART short list.")
            with st.expander("View Short List", expanded=False):
                st.write(corp_short_list_data)

            with st.spinner("🔢 Generating DART corporation code..."):
                corp_code_data = await generate_corp_code(full_name, corp_short_list_data)
                report_data['corp_code_data'] = corp_code_data

            if not corp_code_data or "error" in corp_code_data or corp_code_data.get('corp_code') == 'N/A':
                st.info(
                    f"ℹ️ Could not found company data in Dart Using web search instead.")
                if "raw_content" in corp_code_data: st.expander("Raw LLM Output").write(corp_code_data["raw_content"])
                use_web_search = True
                web_search_reason = "corp code generation failed"
            else:
                st.success("✅ DART Corporation code generated.")
                with st.expander("View Corporation Code", expanded=False):
                    st.json(corp_code_data)
                corp_code_value = corp_code_data['corp_code']

        if use_web_search:
            # Use web search when DART information is not available
            report_source = 'web'
            report_data['report_source'] = report_source
            report_data['web_search_reason'] = web_search_reason

            with st.expander('📊 Research Logs', expanded=True):
                logs_container = st.empty()
                logs_container.info("Logs will appear here as the research progresses...")
            reports_container = st.empty()
            reports_container.info("The final report will be displayed here once generated.")

            report, images, logs = await dart_get_report(query=query_template, report_source=report_source,
                                                         path=None, logs_container=logs_container,
                                                         report_container=reports_container)
            report_data['report'] = report
            report_data['images'] = images
            report_data['logs'] = logs
            st.success("✅ Report generated using web search!")
        else:
            # Company found in DART - proceed with filing download and report generation
            st.info("✅ Company found in DART. Proceeding with DART filing download and report generation.")

            with tempfile.TemporaryDirectory() as temp_dir:
                with st.spinner("📄 Searching DART filings and downloading documents..."):
                    doc_path = await dart_search(corp_code_value, temp_dir)

                if not doc_path:
                    st.info("❌ Company data is not available in Dart documents. Using web sources instead.")
                    report_source = 'web'
                else:
                    report_source = 'hybrid'

                    display_doc_path = os.path.relpath(doc_path, temp_dir)
                    st.success(f"✅ DART documents processed. Path: {display_doc_path}")
                    with st.expander("View Document Path", expanded=False):
                        st.write(display_doc_path)

                report_data['report_source'] = report_source

                with st.expander('📊 Research Logs', expanded=True):
                    logs_container = st.empty()
                    logs_container.info("Logs will appear here as the research progresses...")
                reports_container = st.empty()
                reports_container.info("The final report will be displayed here once generated.")

                report, images, logs = await dart_get_report(query=query_template, report_source=report_source,
                                                             path=doc_path, logs_container=logs_container,
                                                             report_container=reports_container)
                report_data['report'] = report
                report_data['images'] = images
                report_data['logs'] = logs
                st.success("✅ Success! Report generated using DART filings!")

    st.session_state.report_to_display = report_data
    st.session_state.report_list.append(report_data)

    # Display images if any
    if images:
        st.subheader("🖼️ Report Images")
        for i, image_data in enumerate(images):
            # Assuming image_data could be URL, path, or bytes. St.image handles these.
            st.image(image_data, caption=f"Report Image {i + 1}")


# Main content area
if generate_button and company_url:
    try:
        if (company_url, language) in [(company_report["url"], company_report["language"]) for company_report in
                                       st.session_state.report_list]:
            st.info("⚠️ Report already generated for this company and language.")
        else:
            asyncio.run(generate_report_flow(company_url, language))
    except Exception as e:
        st.error(f"❌ An unexpected error occurred in the main application flow: {str(e)}")
        st.exception(e)  # Shows the full traceback in the Streamlit app

elif generate_button and not company_url:
    st.warning("⚠️ Please enter a company URL to generate the report.")

elif st.session_state.report_to_display:
    display_report(st.session_state.report_to_display)

else:
    # Welcome message (no changes here)
    st.markdown("""
    ## Welcome to the Investment Report Generator! 👋

    This application helps you generate comprehensive investment reports for companies using:

    - **SEC Filings** (for English/US companies)
    - **DART Filings** (for Korean companies)

    ### How to use:
    1. Select your preferred language (English or Korean)
    2. Enter the company's website URL
    3. Click "Generate Report" to start the analysis

    ### Features:
    - 🔍 Automatic company information extraction
    - 📄 Filing search and analysis
    - 📊 Comprehensive investment memorandum generation
    - 🖼️ Visual report elements (if generated)
    - 📥 Download reports as markdown files

    **Get started by entering a company URL in the sidebar!**
    """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>IM Report Generator | Powered by doAZ</p>
    </div>
    """,
    unsafe_allow_html=True
)
