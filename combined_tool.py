import itertools
from google.genai import Client, types


def get_answer_to_query(query:str, tools_list: list) -> str:
    tools = list(itertools.chain.from_iterable(tools_list))
    client = Client()

    config = types.GenerateContentConfig(
        tools=tools)  # Pass the function itself

    # Make the request
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=query,
        config=config,
    )

    return response.text