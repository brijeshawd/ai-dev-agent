from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from llm import llm
from config import GITHUB_TOKEN, JIRA_TOKEN, JIRA_EMAIL, JIRA_HOST
import os

class MCPAgent:
    def __init__(self):
        self.chain = None

    async def setup(self):

        client = MultiServerMCPClient(
            {
                "git": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@cyanheads/git-mcp-server"],
                    "env": {
                        "GITHUB_TOKEN": GITHUB_TOKEN
                    }
                },
                "jira": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@aashari/mcp-server-atlassian-jira"],
                    "env": {
                        "ATLASSIAN_SITE_NAME": JIRA_HOST.replace("https://", "").replace(".atlassian.net", ""),
                        "ATLASSIAN_USER_EMAIL": JIRA_EMAIL,
                        "ATLASSIAN_API_TOKEN": JIRA_TOKEN
                    }
                },
                "github": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN }
                }

            }
        )

        print("🔄 Loading MCP tools...")
        tools = await client.get_tools()

        if not tools:
            raise Exception("❌ No MCP tools loaded")

        self.tools = tools  # Store tools for execution
        print(f"✅ MCP Tools Loaded: {len(tools)}")

        for t in tools:
            print("🔧 Tool:", t.name)

        print("🔗 Binding tools to LLM...")
        # ✅ Bind tools directly to LLM (NEW WAY)
        llm_with_tools = llm.bind_tools(tools)

        print("📝 Creating prompt template...")
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an AI DevOps agent.
Use tools for Jira and Git operations.
Do not answer without tools when required."""),
            ("human", "{input}")
        ])

        print("🔗 Creating runnable chain...")
        # ✅ Runnable chain (modern replacement of AgentExecutor)
        self.chain = prompt | llm_with_tools
        
        print("✅ Agent setup complete!")

mcp_agent = MCPAgent()
