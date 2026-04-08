import asyncio
from graph import build_graph
from agent import mcp_agent
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

async def get_user_input(stage):
    """Ask user for approval interactively"""
    while True:
        user_input = input(f"\n👉 Approve {stage}? (yes/no): ").strip().lower()
        if user_input in ["yes", "y"]:
            return True
        elif user_input in ["no", "n"]:
            feedback = input("💬 Enter feedback: ")
            return {"approved": False, "feedback": feedback}
        else:
            print("❌ Invalid input. Type 'yes' or 'no'.")

async def main():
    print("🚀 Starting main application...")
    await mcp_agent.setup()
    print("✅ MCP agent setup complete")

    graph = build_graph()
    print("✅ Graph built")

    # ---------------- INITIAL INVOKE ----------------
    try:
        state = await graph.ainvoke(
            {"jira_id": "MDP-12"},
            config={"configurable": {"thread_id": "1"}}
        )
    except GraphInterrupt as exc:
        state = exc.value
        print("\n⏸️ Workflow paused after initial fetch/extract/fanout")

    print(f"\n📊 State after initial invoke: {state}")

    # ---------------- DEV APPROVAL ----------------
    dev_input = await get_user_input("DEV")

    try:
        if dev_input is True:
            state = await graph.ainvoke(
                Command(resume={"approved_dev": True}),
                config={"configurable": {"thread_id": "1"}}
            )
        else:
            state = await graph.ainvoke(
                Command(resume={
                    "approved_dev": False,
                    "feedback": dev_input["feedback"]
                }),
                config={"configurable": {"thread_id": "1"}}
            )
    except GraphInterrupt as exc:
        state = exc.value
        print("\n⏸️ Workflow paused again after dev review")

    print(f"\n📊 State after dev step: {state}")

    # ---------------- LEAD APPROVAL ----------------
    lead_input = await get_user_input("LEAD")

    try:
        if lead_input is True:
            state = await graph.ainvoke(
                Command(resume={"approved_lead": True}),
                config={"configurable": {"thread_id": "1"}}
            )
        else:
            state = await graph.ainvoke(
                Command(resume={
                    "approved_lead": False,
                    "feedback": lead_input["feedback"]
                }),
                config={"configurable": {"thread_id": "1"}}
            )
    except GraphInterrupt as exc:
        state = exc.value
        print("\n⏸️ Workflow paused again after lead review")

    print(f"\n📊 Final State: {state}")

asyncio.run(main())
