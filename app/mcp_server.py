from mcp.server.fastmcp import FastMCP

# Create a FastMCP server named "CalManage Server"
mcp = FastMCP("CalManage Server")

@mcp.tool()
def schedule_meeting(title: str, date_time: str, attendee: str) -> str:
    """Schedule a meeting on the calendar.

    Args:
        title: The meeting title.
        date_time: The date and time (e.g., '2026-06-30 at 3:00 PM').
        attendee: The name or email of the attendee.
    """
    return f"Successfully scheduled meeting '{title}' with {attendee} on {date_time}."

@mcp.tool()
def get_meetings() -> str:
    """Retrieve all scheduled meetings from the calendar."""
    return "Scheduled meetings:\n1. 10:00 AM - Daily Standup with Team\n2. 2:00 PM - Q2 Review with Bob"

@mcp.tool()
def add_task(title: str, due_date: str = "Today") -> str:
    """Add a new task to the to-do list.

    Args:
        title: The task description or title.
        due_date: The due date for the task.
    """
    return f"Successfully added task '{title}' due on {due_date}."

@mcp.tool()
def draft_email(to_address: str, subject: str, body: str) -> str:
    """Draft an email response.

    Args:
        to_address: The recipient email address.
        subject: The subject of the email.
        body: The body content of the email.
    """
    return f"Successfully drafted email to {to_address} with subject '{subject}'.\nBody:\n{body}"

if __name__ == "__main__":
    mcp.run()
