#!/bin/bash

source .venv/bin/activate

python -c "from langgraph.graph import StateGraph" >/dev/null 2>&1
python -c "from langchain_google_genai import ChatGoogleGenerativeAI" >/dev/null 2>&1

python main.py