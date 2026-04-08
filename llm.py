from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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",
    model="openai/gpt-4o-mini",
    temperature=0
)