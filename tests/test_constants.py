from agent.constants import (
    STATUSES, REGIONS, BLOCKER_COLS, ESCALATION_STATUSES,
    OUTREACH_STATUSES, TASK_CATEGORIES, CSV_COL_ACCOUNT_ID,
    CSV_COL_STATUS, CSV_COL_SALES_REGION, CSV_COL_EXPIRATION_DATE,
    CSV_COL_KICKOFF_DATE_HEADER, SYSTEM_PROMPT, DATA_DIR,
)

def test_status_count():
    assert len(STATUSES) == 15

def test_region_count():
    assert len(REGIONS) == 11

def test_blocker_col_count():
    assert len(BLOCKER_COLS) == 14

def test_escalation_statuses_subset_of_statuses():
    for s in ESCALATION_STATUSES:
        assert s in STATUSES

def test_outreach_statuses_subset_of_statuses():
    for s in OUTREACH_STATUSES:
        assert s in STATUSES

def test_task_categories_contains_unclassified():
    assert "UNCLASSIFIED" in TASK_CATEGORIES

def test_task_categories_count():
    assert len(TASK_CATEGORIES) == 7

def test_account_id_col_is_index_zero():
    assert CSV_COL_ACCOUNT_ID == 0

def test_kickoff_date_col_has_newline():
    assert "\n" in CSV_COL_KICKOFF_DATE_HEADER

def test_system_prompt_lists_six_classifiable_categories():
    for cat in ["ESCALATION", "CUSTOMER_OUTREACH", "BLOCKER_REVIEW",
                "STATUS_UPDATE", "PS_ENGAGEMENT", "EXPIRY_RISK"]:
        assert cat in SYSTEM_PROMPT

def test_data_dir_points_to_data_folder():
    assert str(DATA_DIR).endswith("data")
