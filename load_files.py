import pandas as pd
import os
from langchain_community.document_loaders import (
    PyPDFLoader,      # Uses pypdf
    CSVLoader,
    Docx2txtLoader,   # Uses docx2txt
    TextLoader
)
import tempfile
from google.genai import Client, types

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores.faiss import FAISS


DOCUMENT_DESCRIPTION_PROMPT = """Given the following document text, write an LLM tool description. The description should summarize the document's content and specify the types of user questions for which information should be retrieved from this document. Just write the content with no formatting"""

RETRIEVER_DOCSTRING = """
{DOCUMENT_DESCRIPTION}
Args:
    search_phrase (str): A string representing the query or keyword to search
                    for relevant documents in the vector store. This phrase
                    should capture the essence of the user's information need.
                    The search phrase should be in the same language as the 
                    document for more accurate retrievals

Returns context:
    list[str]:A list of strings, where each string is a document (or chunk of a document)
            from the vector store. These documents serve as context to answer the
            user's question.
"""

# --- Retriever Class (as you defined it) ---
class Retriever():
    def __init__(self, documents):
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = FAISS.from_documents(documents=documents, embedding=self.embeddings)
        self.retriever = self.vectorstore.as_retriever()

    def retrieve_documents(self, search_phrase: str) -> list[str]:
        """Retrieves documents based on a given search phrase."""
        retrieved_documents = self.retriever.invoke(search_phrase)
        return [doc.page_content for doc in retrieved_documents]

# --- Function to create specialized retrieval functions ---
def create_specialized_retriever_function(retriever_obj: Retriever, docstring_text: str):
    """
    Creates and returns a specialized retrieval function.

    Args:
        retriever_obj: An instance of the Retriever class.
        docstring_text: The docstring to set for the new function.

    Returns:
        A callable function that takes a search_phrase and uses the provided retriever.
    """
    def specialized_retrieve(search_phrase: str) -> list[str]:
        """
        This is a placeholder docstring. The actual docstring will be set dynamically.
        """
        return retriever_obj.retrieve_documents(search_phrase)

    # Dynamically set the docstring
    specialized_retrieve.__doc__ = docstring_text
    
    return specialized_retrieve


def extract_content_with_specific_loaders(file_path):
    """
    Extracts content from TXT, PDF, CSV, and DOCX files using specified
    Langchain loaders.

    Args:
        file_path (str): The path to the file.

    Returns:
        tuple: (str, list)
            - The extracted content as a single string, or None if an error occurs.
            - A list of Langchain Document objects, or None if an error occurs.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return None, None

    _, file_extension = os.path.splitext(file_path.lower())
    loader = None
    extracted_text = ""
    documents = []

    print(f"Attempting to load file: {file_path} with extension: {file_extension}")

    try:
        if file_extension == ".txt":
            loader = TextLoader(file_path, encoding='utf-8') # Specify encoding for robustness
        elif file_extension == ".pdf":
            loader = PyPDFLoader(file_path)
        elif file_extension == ".csv":
            # CSVLoader by default treats each row as a document.
            # You might want to specify source_column if one column contains the main text.
            loader = CSVLoader(file_path, encoding='utf-8') # Specify encoding
        elif file_extension == ".docx":
            loader = Docx2txtLoader(file_path)
        else:
            print(f"Unsupported file type: {file_extension}")
            return None, None

        if loader:
            print(f"Using loader: {loader.__class__.__name__}")
            documents = loader.load_and_split()  # Returns a list of Document objects
            
            # Concatenate page_content from all Document objects
            for doc in documents:
                if hasattr(doc, 'page_content'):
                    extracted_text += doc.page_content + "\n"
                else:
                    print(f"Warning: Document object from {loader.__class__.__name__} lacks 'page_content'. Doc: {doc}")
            
            print(f"Successfully extracted content. Total characters: {len(extracted_text)}")
            return extracted_text.strip(), documents

    except Exception as e:
        print(f"An error occurred while processing the file {file_path}: {e}")
        # You might want to log the full traceback here for debugging
        # import traceback
        # print(traceback.format_exc())
        return None, None

def create_vectorstore_and_retriever(client:Client, text:str, documents):
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=f"{DOCUMENT_DESCRIPTION_PROMPT}\n\n{text}"
    )
    doc_description = response.text
    tool_description = RETRIEVER_DOCSTRING.format(DOCUMENT_DESCRIPTION=doc_description)
    retriever_instance = Retriever(documents=documents)
    retriever_function = create_specialized_retriever_function(retriever_obj=retriever_instance, docstring_text=tool_description)
    return retriever_function

def get_retriever_function(file_path:str, client: Client):
    document_text, documents = extract_content_with_specific_loaders(file_path)
    if document_text is None or documents is None:
        raise Exception("Failed to extract the contents of the file")
    return create_vectorstore_and_retriever(client=client, text=document_text, documents=documents)

def excel_to_multiple_csv(excel_file_path: str, output_directory: str = None):
    """
    Converts an Excel file with multiple sheets into separate CSV files,
    one for each sheet.

    Args:
        excel_file_path (str): The path to the input Excel (.xlsx or .xls) file.
        output_directory (str, optional): The directory where the CSV files
                                          will be saved. If None, CSV files
                                          will be saved in the same directory
                                          as the Excel file. Defaults to None.
    Returns:
        bool: True if the conversion was successful, False otherwise.
    """
    if not os.path.exists(excel_file_path):
        print(f"Error: Excel file not found at '{excel_file_path}'")
        return False

    if not excel_file_path.lower().endswith(('.xlsx', '.xls')):
        print(f"Error: The provided file '{excel_file_path}' is not a valid Excel file.")
        return False

    # Determine the output directory
    if output_directory is None:
        output_directory = os.path.dirname(excel_file_path)
        if not output_directory: # If excel_file_path is just a filename in current dir
            output_directory = os.getcwd()
    else:
        # Create the output directory if it doesn't exist
        os.makedirs(output_directory, exist_ok=True)

    print(f"Converting '{excel_file_path}' to CSVs in '{output_directory}'...")

    try:
        # Read all sheets from the Excel file into a dictionary of DataFrames
        # The keys of the dictionary will be the sheet names
        excel_sheets = pd.read_excel(excel_file_path, sheet_name=None)

        if not excel_sheets:
            print("No sheets found in the Excel file.")
            return False

        for sheet_name, df in excel_sheets.items():
            # Sanitize sheet name for filename (replace problematic characters)
            sanitized_sheet_name = "".join(c for c in sheet_name if c.isalnum() or c in (' ', '_')).rstrip()
            csv_filename = f"{sanitized_sheet_name}.csv"
            csv_file_path = os.path.join(output_directory, csv_filename)

            # Write the DataFrame to a CSV file
            df.to_csv(csv_file_path, index=False, encoding='utf-8')
            print(f"  - Successfully created '{csv_file_path}'")

        print("Conversion complete!")
        return True

    except Exception as e:
        print(f"An error occurred during conversion: {e}")
        return False


def process_files_and_get_chat_object(file_path_list: list[str], client:Client):
    tool_list = []
    for file_path in file_path_list:
        if file_path.endswith((".xlsx",".xls")):
            with tempfile.TemporaryDirectory as temp_dir:
                if not excel_to_multiple_csv(file_path, temp_dir):
                    raise Exception("Failed to extract content from excel files")
                for csv_file_path in os.listdir(temp_dir):
                    tool = get_retriever_function(file_path=csv_file_path, client=client)
                    tool_list.append(tool)
        else:
            tool = get_retriever_function(file_path=file_path, client=client)
            tool_list.append(tool)
    
    # config = types.GenerateContentConfig(
        # tools=tool_list
    # )  


    # chat = client.chats.create(model="gemini-2.0-flash", config=config)

    return tool_list