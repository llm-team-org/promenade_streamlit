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
from google.genai import Client # Assuming this is the correct client for chat_object
from load_files import process_files_and_get_chat_object
from dotenv import load_dotenv
load_dotenv()
from sec_agent import run_agent
# Apply nest_asyncio to handle asyncio in Streamlit
nest_asyncio.apply()

# --- Page Constants ---
PAGE_REPORT_GENERATOR = "Report Generator"
PAGE_SEC_CHAT = "SEC Agent Chat"
PAGE_DART_CHAT = "DART Filings Agent Chat"
PAGE_DOCUMENT_CHAT = "Chat with Document" # Renamed from PAGE_PDF_CHAT

# --- Page Configuration and Session State Initialization ---

def setup_page_config():
    """Sets up the Streamlit page configuration."""
    st.set_page_config(
        page_title="IM Draft Generator",
        page_icon="📊",
        layout="wide"
    )

def init_session_state():
    """Initializes session state variables if they don't exist."""
    if 'report_list' not in st.session_state:
        st.session_state.report_list = []
    if 'report_to_display' not in st.session_state:
        st.session_state.report_to_display = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = PAGE_REPORT_GENERATOR
    if 'uploaded_files' not in st.session_state: # Renamed from uploaded_pdfs
        st.session_state.uploaded_files = []
    if 'selected_file_for_chat' not in st.session_state: # Renamed from selected_pdf_for_chat
        st.session_state.selected_file_for_chat = None
    if 'last_filings_selection' not in st.session_state:
        st.session_state.last_filings_selection = "Global SEC filings"
    if 'last_company_url' not in st.session_state:
        st.session_state.last_company_url = ""
    if 'google_client' not in st.session_state:
        st.session_state.google_client = Client()
    if 'chat_histories' not in st.session_state: # New: Store chat history per document
        st.session_state.chat_histories = {}
    if 'sec_agent_query_answer' not in st.session_state:
        st.session_state.sec_agent_query_answer = []

# --- Helper Functions for UI and State Management ---

def set_report_to_display(report):
    """Sets the report to be displayed in the main content area."""
    st.session_state.report_to_display = report

def remove_report_from_list(report_to_remove):
    """Removes a report from the report_list in session state."""
    st.session_state.report_list = [
        report for report in st.session_state.report_list if report != report_to_remove
    ]
    # If the removed report was currently displayed, clear the display
    if st.session_state.report_to_display == report_to_remove:
        st.session_state.report_to_display = None

def navigate_to(page_name):
    """Sets the current page in session state for navigation."""
    st.session_state.current_page = page_name
    # Clear main display when navigating to a chat page
    # if page_name != PAGE_REPORT_GENERATOR:
    st.session_state.report_to_display = None

# --- UI Rendering Functions ---

def display_report_details(report_data):
    """Displays the comprehensive report details in the main content area."""
    company_data = report_data.get('company_data', {})
    if not company_data or "error" in company_data:
        st.error(f"❌ Failed to extract company information: {company_data.get('error', 'Unknown error')}")
        if "raw_content" in company_data:
            st.expander("Raw LLM Output").write(company_data["raw_content"])
        return

    st.success("✅ Company information extracted successfully!")

    # Display company data
    st.subheader("📋 Company Information")
    with st.expander("View Company Details", expanded=True):
        st.json(company_data)

    full_name = company_data.get('company_name', 'N/A')
    first_name = company_data.get('company_first_name', 'N/A')
    ticker = company_data.get('ticker', 'N/A')

    if full_name == 'N/A':
        st.error("❌ Company name could not be determined. Cannot proceed.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Company Name", full_name)
    with col2:
        st.metric("First Name", first_name)
    with col3:
        st.metric("Ticker", ticker)

    st.markdown("---")

    selected_language = report_data.get('language', '')
    report = report_data.get('report', '')
    images = report_data.get('images', [])

    if selected_language.lower() == "english":
        st.subheader("🇺🇸 SEC Filing Analysis")
        filings_data = report_data.get('filings_data', {})

        if not filings_data or not filings_data.get('filings'):
            st.warning("⚠️ No SEC filings found or error in fetching.")
        else:
            st.success(f"✅ Found {len(filings_data.get('filings', []))} SEC filings.")
            with st.expander("View SEC Filings", expanded=False):
                st.json(filings_data)

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

    if report:
        st.subheader(f"📈 {selected_language.capitalize()} Investment Report")
        company_name_clean = full_name.replace(' ', '_').replace('/', '_').replace('\\', '_')

        with st.expander("View Full Report", expanded=True):
            st.markdown(report)
    else:
        st.info("ℹ️ Report generation did not produce output, or path was skipped.")

    if images:
        st.subheader("🖼️ Report Images")
        for i, image_data in enumerate(images):
            st.image(image_data, caption=f"Report Image {i + 1}")

def display_welcome_message():
    """Displays the welcome message and instructions."""
    st.markdown("""
    ## Welcome to the Investment Report Generator! 👋

    This application helps you generate comprehensive investment reports for companies using:

    - **SEC Filings** (for English/US companies)
    - **DART Filings** (for Korean companies)

    ### How to use:
    1. Select your preferred **filings type** (Global SEC or Korean DART) above.
    2. Enter the **company's website URL** in the input field.
    3. Click "**🚀 Generate Report**" to start the analysis.

    ### Features:
    - 🔍 Automatic company information extraction
    - 📄 Filing search and analysis
    - 📊 Comprehensive investment memorandum generation
    - 🖼️ Visual report elements (if generated)
    - 📥 Download reports as markdown files

    **Get started by filling out the details above!**
    """)


# --- Placeholder Functions for Agent Logic (to be implemented by you) ---

def process_uploaded_file(uploaded_file):
    """
    Processes the uploaded file (e.g., extracts text, creates embeddings)
    and initializes a chat object.
    Returns a dictionary containing file info and the chat object.
    """
    if uploaded_file:
        file_extension = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            file_path = tmp_file.name
            # Assuming process_files_and_get_chat_object initializes a chat session
            # and that st.session_state.google_client is the correct client object.
            chat_object = process_files_and_get_chat_object(file_path_list=[file_path], client=st.session_state.google_client)
        st.success(f"Document '{uploaded_file.name}' processed and ready for chat.")
        return {"name": uploaded_file.name, "path": file_path, "id": os.path.basename(file_path), 'chat_obj': chat_object}
    return None

def query_document_chat(processed_file_info, user_query):
    """
    Handles querying the processed document file with the user's input using the chat object.
    Displays tool call queries and results if present.
    """
    if not processed_file_info or not processed_file_info.get('chat_obj'):
        return "Please select a document file to chat with."

    chat_obj = processed_file_info['chat_obj']
    response_content = []
    tool_interactions = []

    try:
        # Send the message and get the response
        # The send_message method automatically handles tool calls and responses internally
        # if the model is configured with tools.
        result = chat_obj.send_message(user_query)

        # Iterate through the parts of the response to display text and tool interactions
        for part in result.candidates[0].content.parts:
            if hasattr(part, 'text'):
                response_content.append(part.text)
            elif hasattr(part, 'function_call'):
                # This indicates the model wants to call a tool
                tool_call = part.function_call
                tool_interactions.append(f"**Tool Call:** `Function: {tool_call.name}, Args: {tool_call.args}`")
            elif hasattr(part, 'function_response'):
                # This indicates the result of a tool call
                tool_response = part.function_response
                tool_interactions.append(f"**Tool Result for {tool_response.name}:** `{tool_response.response}`")

    except Exception as e:
        response_content.append(f"Error communicating with the AI: {str(e)}")
        # In case of an error, ensure chat history is not corrupted
        print(f"Error in query_document_chat: {e}")

    # Combine tool interactions and AI's text response for display
    final_display_text = ""
    if tool_interactions:
        final_display_text += "\n\n".join(tool_interactions) + "\n\n"
    final_display_text += "\n".join(response_content)

    return final_display_text


# --- UI Rendering Functions (Pages) ---
def render_sidebar_navigation():
    """Renders the navigation buttons in the sidebar."""
    st.sidebar.header("Navigation")
    if st.sidebar.button("📊 Report Generator", key="nav_report_gen"):
        navigate_to(PAGE_REPORT_GENERATOR)
    if st.sidebar.button("🤖 SEC Agent Chat", key="nav_sec_chat"):
        navigate_to(PAGE_SEC_CHAT)
    # if st.sidebar.button("🇰🇷 DART Filings Agent Chat", key="nav_dart_chat"):
    #     navigate_to(PAGE_DART_CHAT)
    if st.sidebar.button("📄 Chat with DOCUMENT", key="nav_document_chat"):
        navigate_to(PAGE_DOCUMENT_CHAT)

def render_report_generator_page():
    """Renders the main Report Generator page content."""
    st.title("📊IM Draft Generator")
    st.markdown("Generate comprehensive investment reports for companies using SEC or DART filings")

    st.markdown("---")

    # --- Section: Generate New Report ---
    st.header("✨ Generate New Report")
    with st.container(border=True):
        col1, col2 = st.columns([1, 2])

        with col1:
            filings_selection = st.selectbox(
                "Select filings:",
                ["Global SEC filings", "Korean Dart fillings"],
                index=["Global SEC filings", "Korean Dart fillings"].index(st.session_state.last_filings_selection)
            )
            language = "english" if filings_selection == "Global SEC filings" else "korean"
            st.session_state.last_filings_selection = filings_selection # Update session state

        with col2:
            company_url = st.text_input(
                "Enter Company URL:",
                value=st.session_state.last_company_url,
                placeholder="https://example.com"
            )
            st.session_state.last_company_url = company_url # Update session state

        generate_button = st.button("🚀 Generate Report", type="primary")

    if generate_button:
        if not company_url:
            st.warning("⚠️ Please enter a company URL to generate the report.")
        else:
            is_duplicate = any(
                r["url"] == company_url and r["language"] == language
                for r in st.session_state.report_list
            )
            if is_duplicate:
                st.info("⚠️ A report for this company and language has already been generated. Displaying the existing report.")
                existing_report = next(
                    (r for r in st.session_state.report_list if r["url"] == company_url and r["language"] == language),
                    None
                )
                if existing_report:
                    set_report_to_display(existing_report)
            else:
                try:
                    asyncio.run(generate_report_flow_async(company_url, language))
                except Exception as e:
                    st.error(f"❌ An unexpected error occurred during report generation: {str(e)}")
                    st.exception(e)

    st.markdown("---")

    # --- Section: Generated Reports ---
    st.header("📄 Generated Reports")
    if not st.session_state.report_list:
        st.info("No reports generated yet. Use the section above to create one!")
    else:
        # Display button for each report in st.session_state.report_list
        for i, report_data in enumerate(st.session_state.report_list):
            col1,col2, col3 = st.columns([2,1,1])
            with col1:
                company_full_name = report_data['company_data']['company_name'].replace(' ', '_').replace('/', '_').replace('\\', '_')
                st.button(
                    f"View {company_full_name}_{report_data['language']} Report",
                    on_click=set_report_to_display,
                    args=(report_data,),
                    key=f"view_report_{i}",  # Unique key for each view button
                    type="primary",
                    use_container_width=True
                )
            with col2:
                company_full_name = report_data['company_data']['company_name'].replace(' ', '_').replace('/', '_').replace('\\', '_')
                filename = f"{company_full_name}_{report_data['language']}_report.md"
                st.download_button(
                    label="📥 Download Report",
                    key=f"download_report_{i}",
                    data=report_data['report'],
                    file_name=filename,
                    mime="text/markdown",
                    use_container_width=True
                )
            with col3:
                st.button(
                    "❌ Remove",
                    on_click=remove_report_from_list,
                    args=(report_data,),
                    key=f"delete_report_{i}",  # Unique key for each delete button
                    use_container_width=True
                )
    st.markdown("---")

    # --- Section: Report Display Area ---
    if st.session_state.report_to_display:
        st.header("📊 Current Report Details")
        display_report_details(st.session_state.report_to_display)
        if st.button("Clear Report Display", help="Click to hide the currently displayed report details."):
            set_report_to_display(None)
    elif not generate_button and not st.session_state.report_to_display:
        display_welcome_message()


def sec_agent_chat_page():
    """Renders the SEC Agent Chat page."""
    st.title("🤖 SEC Agent Chat")
    st.markdown("Chat with an AI agent knowledgeable about **SEC filings**.")

    for query_answer in st.session_state.sec_agent_query_answer:
        with st.container(border=True):
            with st.chat_message('user'):
                st.write(query_answer['query'])
            with st.chat_message('assistant'):
                st.write(query_answer['answer'])
    
    user_query = st.chat_input("Ask me any query regarding SEC filings:")
    if user_query:
        with st.container(border=True):
            with st.chat_message("user"):
                st.write(user_query)
            with st.spinner("Getting answer from SEC Agent"):
                answer = asyncio.run(run_agent(user_query))
            if not answer:
                answer = "Failed to get answer from agent"
            new_query_answer = {'query':user_query, 'answer':answer}
            st.session_state.sec_agent_query_answer.append(new_query_answer)
            st.rerun()

def dart_agent_chat_page():
    """Renders the DART Filings Agent Chat page."""
    st.title("🇰🇷 DART Filings Agent Chat")
    st.markdown("Chat with an AI agent knowledgeable about **Korean DART filings**.")
    st.info("*(This page is under construction. Your DART chat logic will go here.)*")

    # Example chat input (you'll integrate your LLM logic here)
    user_query = st.text_input("Ask me about DART filings:")
    if user_query:
        st.write(f"**You:** {user_query}")
        st.write(f"**DART Agent:** (Simulated response) I can help you understand information from DART reports.")
        # Your actual DART chat agent logic would go here.
        # For example: response = your_dart_agent.query(user_query)
        # st.write(response)

def document_chat_page():
    """Renders the Chat with Document page."""
    st.title("📄 Chat with Your Document")
    st.markdown("Upload a document and chat with its content.")

    # Document Upload Section
    st.subheader("Upload Document")
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["pdf", "txt", "csv", "docx", "xlsx"],
        key="file_uploader"
    )
    if uploaded_file:
        existing_file_names = [file['name'] for file in st.session_state.uploaded_files]
        if uploaded_file.name not in existing_file_names:
            with st.spinner(f"Processing {uploaded_file.name}..."):
                processed_info = process_uploaded_file(uploaded_file)
                if processed_info:
                    st.session_state.uploaded_files.append(processed_info)
                    st.session_state.selected_file_for_chat = processed_info
                    # Initialize chat history for this new document
                    st.session_state.chat_histories[processed_info['id']] = []
                else:
                    st.error("Failed to process document.")
        else:
            st.info(f"Document '{uploaded_file.name}' is already uploaded and processed.")
            st.session_state.selected_file_for_chat = next(
                (f for f in st.session_state.uploaded_files if f['name'] == uploaded_file.name), None
            )

    # Select Document to Chat With
    st.subheader("Select Document to Chat With")
    if st.session_state.uploaded_files:
        file_names = [file['name'] for file in st.session_state.uploaded_files]
        selected_name = st.selectbox(
            "Choose a processed document:",
            options=["-- Select a Document --"] + file_names,
            index=0 if not st.session_state.selected_file_for_chat else
                  (file_names.index(st.session_state.selected_file_for_chat['name']) + 1 if st.session_state.selected_file_for_chat['name'] in file_names else 0),
            key="file_selector"
        )

        # Update selected_file_for_chat based on dropdown selection
        if selected_name != "-- Select a Document --":
            newly_selected_file = next(
                (file for file in st.session_state.uploaded_files if file['name'] == selected_name), None
            )
            if newly_selected_file and newly_selected_file != st.session_state.selected_file_for_chat:
                st.session_state.selected_file_for_chat = newly_selected_file
                # Ensure chat history is initialized for the newly selected document
                if newly_selected_file['id'] not in st.session_state.chat_histories:
                    st.session_state.chat_histories[newly_selected_file['id']] = []
                st.success(f"You are now chatting with: **{st.session_state.selected_file_for_chat['name']}**")
                # Rerun to clear chat input and display relevant history
                st.rerun()
        else:
            st.session_state.selected_file_for_chat = None

    else:
        st.info("Upload a document above to begin chatting with it.")

    # Chat Interface
    st.subheader("Chat Interface")
    if st.session_state.selected_file_for_chat:
        current_file_id = st.session_state.selected_file_for_chat['id']

        # Display chat messages from history
        for message in st.session_state.chat_histories[current_file_id]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        user_query = st.chat_input("Ask a question about the document:", key="document_chat_query")

        if user_query:
            # Add user message to chat history
            st.session_state.chat_histories[current_file_id].append({"role": "user", "content": user_query})
            with st.chat_message("user"):
                st.markdown(user_query)

            with st.spinner("Getting response..."):
                response_content = query_document_chat(st.session_state.selected_file_for_chat, user_query)

            # Add AI response to chat history
            st.session_state.chat_histories[current_file_id].append({"role": "assistant", "content": response_content})
            with st.chat_message("assistant"):
                st.markdown(response_content)

            st.rerun() # Rerun to update the chat display
    else:
        st.info("Select a document from the list above to start chatting.")


# --- Core Report Generation Logic (Moved from main, unchanged) ---

async def generate_report_flow_async(company_url_input, selected_language):
    """
    Handles the asynchronous flow of generating an investment report.
    Fetches company info, then proceeds with SEC or DART filings.
    """
    report_data = {'url': company_url_input, 'language': selected_language}
    st.session_state.report_to_display = None # Clear previous display during generation

    # Step 1: Generate company information
    with st.spinner("🔍 Analyzing company information..."):
        company_data = await generate_company_information(company_url_input, selected_language)
        report_data['company_data'] = company_data

    if not company_data or "error" in company_data:
        st.error(f"❌ Failed to extract company information: {company_data.get('error', 'Unknown error')}")
        if "raw_content" in company_data:
            st.expander("Raw LLM Output").write(company_data["raw_content"])
        return

    st.success("✅ Company information extracted successfully!")

    full_name = company_data.get('company_name', 'N/A')
    first_name = company_data.get('company_first_name', 'N/A')

    if full_name == 'N/A':
        st.error("❌ Company name could not be determined. Cannot proceed.")
        return

    english_query_template = f"""As an investment associate, draft an information memorandum for company: {full_name}
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

    korean_query_template = f"""투자 담당자로서 회사 {full_name}에 대한 정보 메모를 작성하십시오.
    회사 정보: {company_data}
    목차에 다음 내용을 추가하십시오.

    정보 메모에 사용해야 하는 제목은 다음과 같으며, 각 제목에 대한 하위 제목을 생성해야 합니다.
    1. 요약
    2. 투자 주요 내용
    3. 회사 개요
    {full_name} 소개
    연혁, 사명 및 핵심 가치
    글로벌 입지 및 운영
    4. 비즈니스 모델, 전략 및 제품
    5. 사업 부문 심층 분석
    6. 산업 개요 및 경쟁적 포지셔닝
    7. 재무 성과 분석
    8. 경영진 및 기업 지배구조
    9. 전략적 이니셔티브 및 미래 성장 동력
    10. 위험 요소
    11. 투자 고려 사항
    12. 결론
    13. 참고 문헌
    """
    report = ""
    images = []
    logs = ""

    # Placeholder for dynamic logs and report display during generation
    with st.expander('📊 Research Logs', expanded=True):
        logs_container = st.empty()
        logs_container.info("Logs will appear here as the research progresses...")
    reports_container = st.empty()
    reports_container.info("The final report will be displayed here once generated.")

    if selected_language.lower() == "english":
        st.info("Searching SEC filings...")
        with st.spinner("📄 Searching SEC filings..."):
            filings_data = await sec_search(full_name)
            report_data['filings_data'] = filings_data

        if not filings_data or not filings_data.get('filings'):
            st.warning("⚠️ No SEC filings found or error in fetching.")
            urls = []
        else:
            st.success(f"✅ Found {len(filings_data.get('filings', []))} SEC filings.")
            urls = [filing['filingUrl'] for filing in filings_data['filings'] if 'filingUrl' in filing]
            if not urls:
                st.warning("⚠️ No URLs found in SEC filings to generate report from.")

        with st.spinner("📊 Generating comprehensive SEC report..."):
            report, images, logs = await sec_get_report(
                query=english_query_template,
                report_type="research_report",
                sources=urls[:2],
                logs_container=logs_container,
                report_container=reports_container
            )
        st.success("✅ SEC report generation complete!")

    elif selected_language.lower() == "korean":
        st.info("Initiating DART filing analysis...")
        use_web_search = False
        web_search_reason = ""
        corp_code_value = None

        with st.spinner("📝 Generating company short list for DART..."):
            company_first_name_for_dart = first_name if first_name != 'N/A' else full_name.split(" ")[0]
            corp_short_list_data = await short_list(full_name, company_first_name_for_dart)
            report_data['corp_short_list_data'] = corp_short_list_data

        if isinstance(corp_short_list_data, str) and "not in the dart list" in corp_short_list_data.lower():
            st.info("ℹ️ Company not in DART list. Using web search instead.")
            use_web_search = True
            web_search_reason = "not in dart list"
        elif isinstance(corp_short_list_data, str) and "Error" in corp_short_list_data:
            st.info(f"ℹ️ Error in DART lookup: {corp_short_list_data}. Using web search instead.")
            use_web_search = True
            web_search_reason = "error in dart lookup"
        elif not corp_short_list_data:
            st.info("ℹ️ Company in DART list but not found in short DART list. Using web search instead.")
            use_web_search = True
            web_search_reason = "not in short dart list"
        else:
            st.success("✅ Company found in DART short list.")
            with st.spinner("🔢 Generating DART corporation code..."):
                corp_code_data = await generate_corp_code(full_name, corp_short_list_data)
                report_data['corp_code_data'] = corp_code_data

            if not corp_code_data or "error" in corp_code_data or corp_code_data.get('corp_code') == 'N/A':
                st.info("ℹ️ Could not find company data in DART. Using web search instead.")
                if "raw_content" in corp_code_data:
                    st.expander("Raw LLM Output").write(corp_code_data["raw_content"])
                use_web_search = True
                web_search_reason = "corp code generation failed"
            else:
                st.success("✅ DART Corporation code generated.")
                corp_code_value = corp_code_data['corp_code']

        report_source = 'web' if use_web_search else 'hybrid' # Default to hybrid if DART data found
        report_data['report_source'] = report_source
        report_data['web_search_reason'] = web_search_reason

        doc_path = None
        if not use_web_search:
            with tempfile.TemporaryDirectory() as temp_dir:
                with st.spinner("📄 Searching DART filings and downloading documents..."):
                    doc_path = await dart_search(corp_code_value, temp_dir)

                if not doc_path:
                    st.info("❌ Company data is not available in DART documents. Using web sources instead.")
                    report_source = 'web' # Override to web if no documents found
                    report_data['report_source'] = report_source
                else:
                    st.success(f"✅ DART documents processed.")

        with st.spinner(f"📊 Generating comprehensive DART report using {report_source} sources..."):
            report, images, logs = await dart_get_report(
                query=korean_query_template,
                report_source=report_source,
                path=doc_path,
                logs_container=logs_container,
                report_container=reports_container
            )
        st.success("✅ DART report generation complete!")

    report_data['report'] = report
    report_data['images'] = images
    report_data['logs'] = logs

    # Append to report list and set for display
    st.session_state.report_list.append(report_data)
    st.session_state.report_to_display = report_data
    st.rerun()


# --- Main Application Runner ---

def main():
    """Main function to run the Streamlit application."""
    setup_page_config()
    init_session_state()

    # Render sidebar navigation first
    # render_sidebar_navigation()
    st.session_state.current_page = PAGE_REPORT_GENERATOR

    # Determine which page to display based on session state
    if st.session_state.current_page == PAGE_REPORT_GENERATOR:
        render_report_generator_page()
    elif st.session_state.current_page == PAGE_SEC_CHAT:
        sec_agent_chat_page()
    elif st.session_state.current_page == PAGE_DART_CHAT:
        dart_agent_chat_page()
    elif st.session_state.current_page == PAGE_DOCUMENT_CHAT:
        document_chat_page()

    # Footer always at the bottom
    # st.markdown("---")
    # st.markdown(
    #     """
    #     <div style='text-align: center'>
    #         <p>IM Report Generator | Powered by doAZ</p>
    #     </div>
    #     """,
    #     unsafe_allow_html=True
    # )

if __name__ == "__main__":
    main()