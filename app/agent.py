# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import json
from typing import Any
from google.adk.workflow import Workflow, START, Edge, node
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App
from google.genai import types

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# Define MCP server connection details
mcp_connection = StdioConnectionParams(
    server_params=StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "app.mcp_server"],
    )
)

# Create toolsets per agent role
mcp_scheduler = McpToolset(
    connection_params=mcp_connection,
    tool_filter=["schedule_meeting", "get_meetings"]
)

mcp_task = McpToolset(
    connection_params=mcp_connection,
    tool_filter=["add_task"]
)

mcp_email = McpToolset(
    connection_params=mcp_connection,
    tool_filter=["draft_email"]
)

# Specialized Sub-Agents with MCP Tools wired in
scheduler_agent = LlmAgent(
    name="scheduler_agent",
    model=config.model,
    instruction="""You are a scheduling assistant. Your job is to manage calendar events.
Use your calendar tools to view or schedule events as needed.""",
    description="Manages meetings and calendar events.",
    tools=[mcp_scheduler]
)

task_agent = LlmAgent(
    name="task_agent",
    model=config.model,
    instruction="""You are a task management assistant. Your job is to manage the to-do list.
Use your task tools to add new tasks.""",
    description="Manages tasks, to-dos, and task lists.",
    tools=[mcp_task]
)

email_agent = LlmAgent(
    name="email_agent",
    model=config.model,
    instruction="""You are an email assistant. Your job is to draft email replies.
Use your email tools to draft email replies.""",
    description="Drafts email replies and reads email messages.",
    tools=[mcp_email]
)

# Orchestrator
orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""You are the CalManage Orchestrator.
Your job is to route the user's request to the appropriate specialist:
- For scheduling, meetings, and calendar events: scheduler_agent
- For tasks, to-dos, and lists: task_agent
- For email drafting, checking, or replying: email_agent

Call the appropriate agent tool. Once you get the result, formulate a helpful response for the user.""",
    tools=[AgentTool(scheduler_agent), AgentTool(task_agent), AgentTool(email_agent)]
)

@node
def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    user_text = ""
    if isinstance(node_input, str):
        user_text = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        user_text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, dict) and "parts" in node_input:
        parts = node_input["parts"]
        if isinstance(parts, list):
            user_text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in parts)
    else:
        user_text = str(node_input)
    
    # 1. Prompt Injection Detection
    injection_detected = False
    injection_keywords = [
        "ignore previous instructions",
        "bypass safety",
        "you are now",
        "override instructions",
        "system prompt",
        "jailbreak",
        "developer mode"
    ]
    if config.injection_detection_enabled:
        for kw in injection_keywords:
            if kw in user_text.lower():
                injection_detected = True
                break
                
    # 2. Domain-Specific Rule: Credential/Secret check
    secret_compromise = False
    secret_keywords = ["password", "api key", "secret token", "private key"]
    for kw in secret_keywords:
        if kw in user_text.lower():
            secret_compromise = True
            break

    # Determine routing
    route = "allow"
    severity = "INFO"
    log_msg = "Request allowed"

    if injection_detected:
        route = "SECURITY_EVENT"
        severity = "CRITICAL"
        log_msg = "Prompt injection attempt detected"
    elif secret_compromise:
        route = "SECURITY_EVENT"
        severity = "WARNING"
        log_msg = "Credential/secret sharing attempt blocked"

    # 3. PII Scrubbing (only if allowed and config.pii_redaction_enabled is True)
    pii_scrubbed = False
    scrubbed_text = user_text
    if route == "allow" and config.pii_redaction_enabled:
        # Regex patterns for emails and phone numbers
        email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
        
        if re.search(email_pattern, user_text):
            scrubbed_text = re.sub(email_pattern, "[EMAIL]", scrubbed_text)
            pii_scrubbed = True
        if re.search(phone_pattern, user_text):
            scrubbed_text = re.sub(phone_pattern, "[PHONE]", scrubbed_text)
            pii_scrubbed = True

    # 4. Structured JSON audit log
    audit_entry = {
        "event": "security_checkpoint_evaluation",
        "severity": severity,
        "original_length": len(user_text),
        "injection_detected": injection_detected,
        "secret_compromise": secret_compromise,
        "pii_scrubbed": pii_scrubbed,
        "message": log_msg,
        "session_id": ctx.session.id
    }
    print(json.dumps(audit_entry))

    if route == "SECURITY_EVENT":
        return Event(output="Security violation detected.", route=route)
    else:
        # Return scrubbed text to the next node
        return Event(output=scrubbed_text, route=route)

@node
def security_violation_handler(node_input: str):
    msg = "Security Violation: Request blocked due to safety policy."
    yield Event(
        content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]),
        output=msg
    )

@node
async def approval_node(ctx: Context, node_input: Any):
    # Extract string from node_input if necessary
    user_text = ""
    if isinstance(node_input, str):
        user_text = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        user_text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, dict) and "parts" in node_input:
        parts = node_input["parts"]
        if isinstance(parts, list):
            user_text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in parts)
    else:
        user_text = str(node_input)

    # Prevent infinite loop in the workflow
    processed_key = f"approved_done_{ctx.run_id}"
    if ctx.state.get(processed_key):
        yield Event(output=user_text, route="auto_approved")
        return

    # Check if approval is required.
    needs_approval = (
        "email" in user_text.lower()
        or "draft" in user_text.lower()
        or "send" in user_text.lower()
        or "delete" in user_text.lower()
    )
    
    if needs_approval:
        if not ctx.resume_inputs or "approved" not in ctx.resume_inputs:
            yield RequestInput(interrupt_id="approved", message="Do you approve this sensitive action? (yes/no)")
            return
        
        user_approval = ctx.resume_inputs["approved"]
        if user_approval.lower() in ["yes", "y", "approve"]:
            ctx.state[processed_key] = True
            yield Event(output="Action approved and executed.", route="approved")
        else:
            yield Event(output="Action denied by user.", route="denied")
    else:
        yield Event(output=user_text, route="auto_approved")

@node
def cancellation_handler(node_input: str):
    msg = f"Operation cancelled: {node_input}"
    yield Event(
        content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]),
        output=msg
    )

# Root agent Workflow using explicit Edge objects
root_agent = Workflow(
    name="calmanage_workflow",
    edges=[
        Edge(from_node=START, to_node=security_checkpoint),
        Edge(from_node=security_checkpoint, to_node=orchestrator, route="allow"),
        Edge(from_node=security_checkpoint, to_node=security_violation_handler, route="SECURITY_EVENT"),
        Edge(from_node=orchestrator, to_node=approval_node),  # Unconditional edge
        Edge(from_node=approval_node, to_node=cancellation_handler, route="denied"),
        Edge(from_node=approval_node, to_node=orchestrator, route="approved"), # Compliant with Edge Rule
    ],
    description="CalManage executive assistant workflow."
)

app = App(
    name="app",
    root_agent=root_agent,
)
