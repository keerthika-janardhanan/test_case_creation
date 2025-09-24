import requests
import os
from requests.auth import HTTPBasicAuth
# from config import JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
from dotenv import load_dotenv

load_dotenv()

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {"Accept": "application/json"}

def fetch_jira_issues(jql_query, max_results=50):
    """
    Fetch issues from Jira using a JQL query.
    Returns a list of issue dicts.
    """
    start_at = 0
    all_issues = []

    while True:
        url = f"{JIRA_BASE_URL}/rest/api/3/search"
        params = {
            "jql": jql_query,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": "summary,description,issuetype,project,status,parent,priority,assignee"
        }

        response = requests.get(url, headers=headers, auth=auth, params=params)
        response.raise_for_status()
        data = response.json()

        issues = data.get("issues", [])
        if not issues:
            break

        all_issues.extend(issues)
        start_at += max_results

        if start_at >= data.get("total", 0):
            break

    return all_issues
