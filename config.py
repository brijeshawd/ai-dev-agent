import os
from dotenv import load_dotenv

load_dotenv()

HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

JIRA_TOKEN = os.getenv("JIRA_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_HOST = os.getenv("JIRA_HOST", "https://abc-def.atlassian.net")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

REPO = "brijeshawd/python"
