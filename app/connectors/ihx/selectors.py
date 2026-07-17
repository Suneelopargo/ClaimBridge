# app/connectors/ihx/selectors.py

"""
IHX Portal UI Selectors

Keep all UI selectors here so connector logic remains stable when the portal UI
changes. Prefer accessible text/role selectors in connector code for Power BI
controls because generated CSS classes can change between sessions.
"""

# ---------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------

LOGIN_URL = "https://provider.ihx.in"
INPATIENT_CLAIMS_URL = "https://provider.ihx.in/claims/in-patient"

# The reconciliation report is reached through the IHX navigation menu.
# Keep this configurable in .env because the direct route may vary.
RECONCILIATION_REPORT_URL_ENV = "IHX_RECONCILIATION_REPORT_URL"


# ---------------------------------------------------------------------
# Login Page
# ---------------------------------------------------------------------

USERNAME = "#login-form_username"
PASSWORD = "#login-form_password"
LOGIN_BUTTON = "button[type='submit']"


# ---------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------

OTP_DIGIT_PREFIX = "[data-testid='otp-{}']"
VERIFY_OTP_BUTTON = "button[type='submit']"


# ---------------------------------------------------------------------
# Claim Summary Page
# ---------------------------------------------------------------------

CLAIMS_TABLE = "table"
CLAIMS_TABLE_HEADER = "table thead"
CLAIMS_TABLE_BODY = "table tbody"
CLAIM_ROWS = "table tbody tr"


# ---------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------

NEXT_PAGE = ".ant-pagination-next"
PREVIOUS_PAGE = ".ant-pagination-prev"
PAGINATION_NEXT = "li.ant-pagination-next"
PAGINATION_NEXT_DISABLED = ".ant-pagination-next.ant-pagination-disabled"


# ---------------------------------------------------------------------
# IHX Navigation
# ---------------------------------------------------------------------

REPORTING_AND_ANALYTICS_TEXT = "Reporting and Analytics"
RECONCILIATION_TEXT = "Reconciliation"


# ---------------------------------------------------------------------
# Power BI export
# ---------------------------------------------------------------------

# These are fallback selectors. The connector first prefers accessible roles
# and visible text because Power BI's generated class names can change.
POWER_BI_IFRAME = "iframe"
EXPORT_DIALOG_TITLE_TEXT = "Which data do you want to export?"
DATA_WITH_CURRENT_LAYOUT_TEXT = "Data with current layout"
SUMMARIZED_DATA_TEXT = "Summarized data"
EXPORT_BUTTON_TEXT = "Export"
CANCEL_BUTTON_TEXT = "Cancel"

# Common Power BI visual menu buttons/fallbacks.


POWER_BI_EXPORT_DATA_MENU_TEXT = "Export data"


# ---------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------

LOADING_SPINNER = ".ant-spin"
SUCCESS_ALERT = ".ant-alert-success"
ERROR_ALERT = ".ant-alert-error"

COOKIE_ACCEPT_BUTTON = "button:has-text('Accept')"
COOKIE_ACCEPT_ALL_BUTTON = "button:has-text('Accept All')"
COOKIE_CLOSE_BUTTON = "button:has-text('Close')"

# ---------------------------------------------------------------------
# Reconciliation page
# ---------------------------------------------------------------------

UPDATE_RECONCILIATION_REPORT_TEXT = "Update Reconciliation Report"

# A column heading expected after the Power BI report has loaded.
# Change this only if the IHX report layout changes.
RECONCILIATION_REPORT_READY_TEXT = "Patient Name"

POWER_BI_MORE_OPTIONS = (
    "button[aria-label*='More options'], "
    "button[title*='More options'], "
    "[role='button'][aria-label*='More options'], "
    "[data-testid*='more-options'], "
    "[aria-label*='More options']"
)


POWER_BI_VISUAL_CONTAINER = (
    ".visual-container, "
    ".visualContainer, "
    "[class*='visual-container'], "
    "[class*='visualContainer'], "
    "[data-visual-id], "
    "visual-container"
)

