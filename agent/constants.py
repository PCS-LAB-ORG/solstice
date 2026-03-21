import re
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
INBOX_DIR = DATA_DIR / "inbox"
STATE_FILE = DATA_DIR / "state.json"
PENDING_TASKS_FILE = DATA_DIR / "pending_tasks.csv"
PENDING_REVIEW_LOG = DATA_DIR / "pending_review.log"
AGENT_LOG = DATA_DIR / "agent.log"
VALIDATION_ERRORS_LOG = DATA_DIR / "validation_errors.log"

# Salesforce account IDs are 15 or 18 alphanumeric characters.
# "TRUE" (4 chars) and "FALSE" (5 chars) are rejected by the length check.
SALESFORCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]{15,18}$")

# --- CSV Column Mapping (by index — column 0 header is '\xa0\xa0', non-breaking spaces) ---
CSV_COL_ACCOUNT_ID = 0
CSV_COL_CUSTOMER_NAME = 1
CSV_COL_ARR = 2
CSV_COL_ACTIVE_CSE = 3
CSV_COL_BACKUP_CSE = 4
CSV_COL_STATUS = 5
CSV_COL_SALES_REGION = 10
CSV_COL_COMMENTS = 12
CSV_COL_EXPIRATION_DATE = 13
CSV_COL_PS_ENGAGED = 36
CSV_COL_KICKOFF_DATE = 35   # column index
CSV_COL_KICKOFF_DATE_HEADER = "Kickoff\nDate"  # actual CSV column header (contains literal newline)
CSV_COL_EMAIL_SENT = 41
# Columns 6-9, 11, 14-34, 37-40 exist in the CSV but are not used by the agent

# Indices 16-30, skipping 19 ('CSP') which is not a blocker column
BLOCKER_COL_INDICES = [16, 17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]
BLOCKER_COLS = [
    "APIs usage / custom integrations / scripts (blocker)",
    "BYOK required?",
    "AgentiX required?",
    "Alibaba or IBM (blocker)",
    "OIDC SSO (blocker)",
    "Custom Compliance (blocker)",
    "Unsupported \nNotifications/Integrations (blocker)",
    "Terraform (provider&onboarding) (blocker)",
    "Agentless AKS/EKS in auto-mode (blocker)",
    "serverless with layers from different accounts (blocker)",
    "serverless runtime protection (blocker)",
    "serverless without internet connection (blocker)",
    "Linux Functions without External Package URL (blocker)",
    "app-embeded protection capabilities (blocker)",
]
if len(BLOCKER_COL_INDICES) != len(BLOCKER_COLS):
    raise ValueError(f"BLOCKER_COL_INDICES ({len(BLOCKER_COL_INDICES)}) and BLOCKER_COLS ({len(BLOCKER_COLS)}) must match")

STATUSES = [
    "Ready To Engage", "Account team contacted", "Upgrade Email Sent",
    "Kick Off Scheduled", "Customer Engaged", "In Progress",
    "Customer Acceptance", "PS", "Completed", "On Hold",
    "Backoff", "Sales Hold", "Blocked: Tech limitation",
    "Churning/Churned", "Cancelled", "Dev testing",
]

REGIONS = [
    "Alps", "Benelux", "CEE", "France", "Germany",
    "Gulf/North Africa", "Nordics", "SEUR", "Saudi/LBS", "Turkey/SA", "UKI",
]

# UNCLASSIFIED is a code-side fallback (set when Claude API fails) — never emitted by the LLM
TASK_CATEGORIES = [
    "ESCALATION", "CUSTOMER_OUTREACH", "BLOCKER_REVIEW",
    "STATUS_UPDATE", "PS_ENGAGEMENT", "EXPIRY_RISK", "UNCLASSIFIED",
]

ESCALATION_STATUSES = ["Backoff", "Sales Hold", "Churning/Churned", "Cancelled"]
OUTREACH_STATUSES = ["Ready To Engage", "Account team contacted"]

CUSTOMER_OUTREACH_STALE_DAYS = 14
EXPIRY_RISK_DAYS = 30

VERTEX_PROJECT = "pa-sase-insights-tools"
VERTEX_REGION = "us-east5"
VERTEX_MODEL = "claude-sonnet-4-6"
CLASSIFIER_MAX_TOKENS = 1024
CLASSIFIER_RETRY_DELAY_S = 5

SYSTEM_PROMPT = (
    "You are a Prisma Cloud CC Migration task classifier for the EMEA team.\n"
    "Classify each account change into exactly one category from: "
    "ESCALATION, CUSTOMER_OUTREACH, BLOCKER_REVIEW, STATUS_UPDATE, PS_ENGAGEMENT, EXPIRY_RISK.\n"
    "Assign priority: HIGH, MEDIUM, or LOW.\n"
    "Write a one-sentence suggested_action in imperative form "
    "(e.g. \"Escalate to regional manager — account moved to Sales Hold\").\n"
    "Return a JSON array only, no prose."
)

PENDING_TASKS_HEADER = [
    "account_id", "customer_name", "region", "cse", "category",
    "priority", "suggested_action", "old_value", "new_value", "detected_at",
]
