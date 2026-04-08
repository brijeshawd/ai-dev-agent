from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Send
from langgraph.checkpoint.memory import MemorySaver
from email_service import send_email
from llm import llm
from agent import mcp_agent
from config import REPO
import json
import re
import os
from typing import TypedDict, Annotated
import operator

# ---------------- MCP TOOL CALL ----------------
async def call_mcp_tool(tool_name, params):
    tool = next((t for t in mcp_agent.tools if t.name == tool_name), None)
    if tool is None:
        raise ValueError(f"Tool {tool_name} not found")

    if hasattr(tool, 'ainvoke'):
        return await tool.ainvoke(params)
    elif hasattr(tool, 'invoke'):
        return tool.invoke(params)

    raise RuntimeError(f"Tool {tool_name} has no invocation method")


# ---------------- STATE ----------------
# ---------------- STATE ----------------
# ---------------- STATE ----------------
class State(TypedDict):
    jira_id: str
    jira_data: str
    branch: str
    repos: list
    file: str
    updates: list 
    worker_results: Annotated[list, operator.add] 
    task: str
    approved_dev: bool
    approved_lead: bool
    feedback: str
    prs: list  # ✅ NEW: Replaces pr_url and pull_number to support multiple PRs


# ---------------- 1️⃣ JIRA NODE ----------------
async def jira_node(state):
    print(f"📋 Fetching Jira: {state['jira_id']}")
    path = f"/rest/api/2/issue/{state['jira_id']}"
    try:
        result = await call_mcp_tool('jira_get', {'path': path})
        print("🧠 RAW JIRA MCP RESPONSE:\n", result)

        if isinstance(result, list) and len(result) > 0:
            data = result[0]
            jira_clean = data.get("text") or data.get("description") or str(data)
        else:
            jira_clean = str(result)

        jira_clean = jira_clean.replace("\\n", "\n").replace("\\t", "\t")
        print("📄 CLEANED JIRA CONTENT:\n", jira_clean)
    except Exception as e:
        print(f"❌ Jira fetch failed: {e}")
        jira_clean = ""

    return {"jira_data": jira_clean, "branch": state["jira_id"]}


# ---------------- 2️⃣ LLM EXTRACTION ----------------
async def extract_node(state):
    print("🤖 Extracting structured data via LLM (STRICT MODE)...")
    jira_text = state.get("jira_data", "")

    if not jira_text.strip():
        print("❌ Jira content is empty")
        return {"repos": [], "file": "pom.xml", "updates": [], "task": ""}

    extraction_prompt = f"""
You are a precise data extraction system.
STRICT RULES:
- ONLY extract from Jira text
Return ONLY valid JSON:
{{
  "repos": [],
  "file": "pom.xml",
  "updates": [
    {{
      "group_id": null,
      "artifact_id": null,
      "old_version": null,
      "new_version": null
    }}
  ],
  "task": null
}}
Jira Text:
{jira_text}
"""
    res = await llm.ainvoke(extraction_prompt)

    def extract_text(res):
        if isinstance(res, list):
            res = res[0]
        if hasattr(res, "content"):
            return res.content
        return str(res)

    raw_output = extract_text(res)
    cleaned = re.sub(r"```json|```", "", raw_output).strip()

    try:
        parsed = json.loads(cleaned)
    except Exception as e:
        print("❌ JSON parse failed:", e)
        return {"repos": [], "file": "pom.xml", "updates": [], "task": ""}

    # LLM self-validation
    validation_prompt = f"""
Validate this JSON using the Jira text.
Return ONLY: VALID or INVALID
Jira:
{jira_text}
JSON:
{json.dumps(parsed, indent=2)}
"""
    val_res = await llm.ainvoke(validation_prompt)
    val_text = extract_text(val_res).strip()
    if "INVALID" in val_text.upper():
        print("❌ LLM output rejected due to hallucination")
        return {"repos": [], "file": "pom.xml", "updates": [], "task": ""}

    print("📦 FINAL EXTRACTED (LLM VERIFIED):")
    print(parsed)
    return {
        "repos": parsed.get("repos", []),
        "file": parsed.get("file", "pom.xml"),
        "updates": parsed.get("updates", []),
        "task": parsed.get("task", "")
    }


# ---------------- 3️⃣ FANOUT ----------------
from langgraph.types import Send

# ---------------- 3️⃣ FANOUT ----------------
from langgraph.types import Send

def fanout(state: dict):
    """Fanout to multiple workers — each worker gets a single repo"""
    sends = [
        Send(
            node="worker",
            arg={
                "repo": repo,
                "file": state["file"],
                "updates": state["updates"],
                "branch": state["branch"],
                "task": state.get("task", "")
            }
        )
        for repo in state.get("repos", [])
    ]

    # Return the list of Send objects directly for the conditional edge
    return sends



import shutil
# ---------------- 4️⃣ WORKER ----------------
# ---------------- 4️⃣ WORKER ----------------
async def worker(payload:dict):
    print(f"🔨 Worker received task for repo: {payload['repo']} with updates: {payload['updates']}")
    repo = payload["repo"]
    repo_name = repo.rstrip("/").split("/")[-1]
    repo_path = f"./repo_{repo_name}"
    branch_name = payload["branch"]

    # --- START OF DIRECTORY CLEANUP LOGIC ---
    if os.path.exists(repo_path):
        print(f"🧹 Removing existing directory: {repo_path}")
        # ignore_errors=True helps bypass Windows file lock issues 
        # that sometimes occur right after a process uses a folder
        shutil.rmtree(repo_path, ignore_errors=True) 
    # --- END OF DIRECTORY CLEANUP LOGIC ---
    print(f"🚀 Processing repo: {repo}")

    await call_mcp_tool('git_clone', {'url': repo, 'localPath': repo_path})
    await call_mcp_tool('git_set_working_dir', {'path': repo_path})

    # --- YOUR BRANCH CREATION LOGIC INTEGRATED HERE ---
    # 1) Checkout main
    try:
        checkout_main = await call_mcp_tool('git_checkout', {'path': repo_path, 'target': 'main'})
        print(f"✅ git_checkout main result: {checkout_main}")
    except Exception as e:
        print(f"⚠️ git_checkout main failed: {e}")

    # 2) Create and/or checkout feature branch
    try:
        # Prefer checkout with branch creation if supported
        checkout_feature = await call_mcp_tool('git_checkout', {'path': repo_path, 'target': branch_name, 'create': True})
        print(f"✅ git_checkout (create branch) result: {checkout_feature}")
    except Exception as e:
        print(f"⚠️ git_checkout (create branch) failed: {e}")
        try:
            branch_result = await call_mcp_tool('git_branch', {'path': repo_path, 'name': branch_name, 'start_point': 'main'})
            print(f"✅ git_branch result: {branch_result}")
            checkout_result = await call_mcp_tool('git_checkout', {'path': repo_path, 'target': branch_name})
            print(f"✅ git_checkout feature branch result: {checkout_result}")
        except Exception as e2:
            print(f"⚠️ git_branch/git_checkout failed: {e2}")
            # Fallback to locally running git commands where needed
            import subprocess
            try:
                subprocess.run(['git', 'checkout', 'main'], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(['git', 'checkout', '-B', branch_name], cwd=repo_path, check=True, capture_output=True)
                print(f"✅ local git checkout -B {branch_name} succeeded")
            except Exception as local_e:
                print(f"❌ local fallback branch creation failed: {local_e}")
    # ---------------------------------------------------

    # Apply dependency updates
    file_path = os.path.join(repo_path, payload["file"])
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        updated_content = content
        for dep in payload["updates"]:
            if not all(k in dep for k in ["group_id", "artifact_id", "old_version", "new_version"]):
                continue
            pattern = (
                rf"(<dependency>.*?<groupId>{re.escape(dep['group_id'])}</groupId>.*?"
                rf"<artifactId>{re.escape(dep['artifact_id'])}</artifactId>.*?"
                rf"<version>){re.escape(dep['old_version'])}(</version>.*?</dependency>)"
            )
            replacement = rf"\g<1>{dep['new_version']}\2"
            updated_content = re.sub(pattern, replacement, updated_content, flags=re.DOTALL)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

    # End of worker function
    # Wraps the result in a list so multiple workers combine into one large list
    return {"worker_results": [f"Changes for {repo_name}:\n{updated_content}"]}


# ---------------- 5️⃣ DEV REVIEW ----------------
# ---------------- 5️⃣ DEV REVIEW ----------------
def dev_review(state):
    # Join the list of strings into one big message for the email
    all_changes = "\n\n".join(state.get('worker_results', []))
    
    send_email("uktk20@gmail.com", "Dev Review Required", f"Changes:\n{all_changes}")
    return interrupt({"stage": "dev"})


# ---------------- 6️⃣ PUSH CODE ----------------
# ---------------- 6️⃣ PUSH CODE ----------------
async def push_code(state):
    branch = state["branch"]

    for repo in state.get("repos", []):
        repo_name = repo.rstrip("/").split("/")[-1]
        repo_path = f"./repo_{repo_name}"
        print(f"📤 Preparing to push code for: {repo_name}")

        # --- START OF ROBUST CHECKOUT LOGIC ---
        try:
            # Prefer checkout with branch creation if supported
            checkout_feature = await call_mcp_tool('git_checkout', {'path': repo_path, 'target': branch, 'create': True})
            print(f"✅ git_checkout (create branch) result: {checkout_feature}")
        except Exception as e:
            print(f"⚠️ git_checkout (create branch) failed: {e}")
            try:
                # Fallback 1: Try creating the branch first, then checking it out
                branch_result = await call_mcp_tool('git_branch', {'path': repo_path, 'name': branch, 'start_point': 'main'})
                checkout_result = await call_mcp_tool('git_checkout', {'path': repo_path, 'target': branch})
                print(f"✅ git_branch/checkout feature branch result: {checkout_result}")
            except Exception as e2:
                print(f"⚠️ git_branch/git_checkout failed: {e2}")
                
                # Fallback 2: Absolute fallback to locally running git commands
                import subprocess
                try:
                    subprocess.run(['git', 'checkout', 'main'], cwd=repo_path, check=True, capture_output=True)
                    subprocess.run(['git', 'checkout', '-B', branch], cwd=repo_path, check=True, capture_output=True)
                    print(f"✅ local git checkout -B {branch} succeeded")
                except Exception as local_e:
                    print(f"❌ local fallback branch checkout failed: {local_e}")
        # --- END OF ROBUST CHECKOUT LOGIC ---

        # Add, commit, and push changes to the remote branch
        try:
            await call_mcp_tool('git_add', {'path': repo_path, 'all': True})
            await call_mcp_tool('git_commit', {'path': repo_path, 'message': f"Auto-update: {branch}"})
            await call_mcp_tool('git_push', {'path': repo_path, 'remote': 'origin', 'branch': branch})
            print(f"🚀 Successfully pushed branch {branch} for {repo_name}")
        except Exception as e:
            print(f"❌ Failed to commit or push for {repo_name}: {e}")

    return {}


# ---------------- 7️⃣ CREATE PR ----------------
# ---------------- 7️⃣ CREATE PR ----------------
async def create_pr(state):
    created_prs = []
    
    for repo_url in state.get("repos", []):
        # Dynamically extract owner and repo from the URL
        # e.g., https://github.com/brijeshawd/python -> owner: brijeshawd, repo: python
        repo_parts = repo_url.rstrip("/").split("/")
        owner, repo_name = repo_parts[-2], repo_parts[-1]
        
        print(f"🔄 Creating PR for {owner}/{repo_name}...")
        try:
            pr = await call_mcp_tool('create_pull_request', {
                'owner': owner,
                'repo': repo_name,
                'head': state['branch'],
                'base': 'main',
                'title': state['branch'],
                'body': "Auto PR generated by AI Dev Agent"
            })
            parsed = json.loads(pr[0]["text"])
            
            # Save the PR details for this specific repo
            created_prs.append({
                "repo": repo_name,
                "owner": owner,
                "pr_url": parsed.get("html_url"),
                "pull_number": parsed.get("number")
            })
            print(f"✅ PR Created: {parsed.get('html_url')}")
        except Exception as e:
            print(f"❌ Failed to create PR for {repo_name}: {e}")

    # Return the list of PRs to update the state
    return {"prs": created_prs}


# ---------------- 8️⃣ LEAD REVIEW ----------------
def lead_review(state):
    # Format all PR URLs for the email
    pr_links = "\n".join([pr["pr_url"] for pr in state.get("prs", [])])
    email_body = f"Please review the following PRs:\n{pr_links}"
    
    send_email("uktk20@gmail.com", "PR Review Required", email_body)
    
    # Pause the graph. The value passed when resuming will be assigned to 'user_input'
    print("⏸️ Graph paused for Lead Review. Awaiting resume...")
    user_input = interrupt("Awaiting lead approval. Please resume with {'approved_lead': True}")
    
    # ✅ FIX: Explicitly update the state with the decision so lead_decision can read it
    return {"approved_lead": user_input.get("approved_lead", False)}


# ---------------- 9️⃣ LEAD DECISION ----------------
def lead_decision(state):
    # This now correctly reads the boolean state updated by lead_review
    if state.get("approved_lead"):
        print("✅ Lead approved. Proceeding to merge.")
        return "merge"
    else:
        print("⚠️ Lead rejected/requested rework. Routing back.")
        return "rework"


# ---------------- 🔟 MERGE ----------------
async def merge(state):
    for pr in state.get("prs", []):
        print(f"🔄 Merging PR #{pr['pull_number']} for {pr['repo']}...")
        try:
            await call_mcp_tool('merge_pull_request', {
                'owner': pr['owner'],
                'repo': pr['repo'],
                'pull_number': pr['pull_number']
            })
            print(f"✅ Successfully merged PR for {pr['repo']}")
        except Exception as e:
            print(f"❌ Failed to merge PR for {pr['repo']}: {e}")
            
    return {}


# ---------------- GRAPH ----------------
# ---------------- GRAPH ----------------
def build_graph():
    g = StateGraph(State)

    g.add_node("jira", jira_node)
    g.add_node("extract", extract_node)
    # ❌ REMOVED: g.add_node("fanout", fanout)
    g.add_node("worker", worker)
    g.add_node("dev", dev_review)
    g.add_node("push", push_code)
    g.add_node("pr", create_pr)
    g.add_node("lead", lead_review)
    g.add_node("merge", merge)

    g.set_entry_point("jira")

    # Edges
    g.add_edge("jira", "extract")
    
    # ✅ ADDED: Use conditional edges for the Send API fanout
    g.add_conditional_edges("extract", fanout) 
    
    # ❌ REMOVED: g.add_edge("extract", "fanout")
    # ❌ REMOVED: g.add_edge("fanout", "worker")
    
    g.add_edge("worker", "dev")  # Triggers automatically after all workers finish
    g.add_edge("dev", "push")
    g.add_edge("push", "pr")
    g.add_edge("pr", "lead")

    # ✅ UPDATED: Route "rework" back to "extract" instead of the removed "fanout" node
    g.add_conditional_edges("lead", lead_decision, {"merge": "merge", "rework": "extract"})
    g.add_edge("merge", END)

    return g.compile(checkpointer=MemorySaver())
