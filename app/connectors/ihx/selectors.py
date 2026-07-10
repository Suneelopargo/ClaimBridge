# app/connectors/ihx/selectors.py

"""
IHX Portal UI Selectors

This module centralizes all Playwright selectors used by the IHX connector.
If the IHX portal UI changes, update the selectors here without modifying
the connector logic.
"""

# ---------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------

LOGIN_URL = "https://provider.ihx.in"

INPATIENT_CLAIMS_URL = "https://provider.ihx.in/claims/in-patient"


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
# Common
# ---------------------------------------------------------------------

LOADING_SPINNER = ".ant-spin"

SUCCESS_ALERT = ".ant-alert-success"

ERROR_ALERT = ".ant-alert-error"

# Cookies
COOKIE_ACCEPT_BUTTON = "button:has-text('Accept')"
COOKIE_ACCEPT_ALL_BUTTON = "button:has-text('Accept All')"
COOKIE_CLOSE_BUTTON = "button:has-text('Close')"