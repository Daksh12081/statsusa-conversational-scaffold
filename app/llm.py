import os

from dotenv import load_dotenv


load_dotenv()


_llm = None


def get_llm():
    global _llm

    if _llm is None:
        # Imported lazily: langchain_google_genai pulls in google's generated
        # generativelanguage client, which is extremely slow to import here.
        # Importing it only when an LLM call actually happens (instead of at
        # module load, via nodes/__init__.py) keeps app startup fast.
        from langchain_google_genai import ChatGoogleGenerativeAI

        _llm = ChatGoogleGenerativeAI(
            model=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0,
        )

    return _llm