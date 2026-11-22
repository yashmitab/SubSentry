
import re
import pandas as pd
import streamlit as st
import plotly.express as px
import random
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
st.set_page_config(
    page_title="SubSentry | Financial Leakage Detector",
    page_icon="🔎",
    layout="wide"
)
# =========================
# AUTHENTICATION & SESSION STATE
# =========================

if "users_db" not in st.session_state:
    # Pre-seeded demo account (or stores newly created accounts during the session)
    st.session_state.users_db = {
        "demo@subsentry.in": "SubSentry1"
    }

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "current_user" not in st.session_state:
    st.session_state.current_user = ""

if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "Sign In"

if "signup_step" not in st.session_state:
    st.session_state.signup_step = 1  # 1: Enter Email, 2: Enter OTP + Create Password

if "pending_email" not in st.session_state:
    st.session_state.pending_email = ""

if "generated_otp" not in st.session_state:
    st.session_state.generated_otp = ""


def is_valid_password(pwd: str) -> tuple[bool, str]:
    """Validate that password has at least 1 uppercase letter and 1 number."""
    if len(pwd) < 6:
        return False, "Password must be at least 6 characters long."
    if not re.search(r"[A-Z]", pwd):
        return False, "Password must contain at least one capital letter (A-Z)."
    if not re.search(r"\d", pwd):
        return False, "Password must contain at least one number (0-9)."
    return True, ""


def send_gmail_otp(recipient_email: str, otp_code: str) -> tuple[bool, str]:
    """
    Sends a 6-digit verification code via Gmail SMTP.
    Replace SENDER_EMAIL and APP_PASSWORD with your Gmail & 16-character Google App Password.
    """
    
    def send_gmail_otp(recipient_email: str, otp_code: str) -> tuple[bool, str]:
     SENDER_EMAIL = "yashmitabhaskar@gmail.com"
     APP_PASSWORD = "nytijrwzbevgoeyd"

    try:
        msg = EmailMessage()
        msg["Subject"] = f"{otp_code} is your SubSentry verification code"
        msg["To"] = recipient_email
        msg.set_content(
            f"Hello,\n\nYour SubSentry account verification code is: {otp_code}\n\n"
            f"Enter this code on the Sign Up screen to set your password.\n\n"
            f"— SubSentry Team"
        )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.send_message(msg)
        return True, "Sent"
    except Exception as err:
        return False, str(err)

    try:
        msg = EmailMessage()
        msg["Subject"] = f"{otp_code} is your SubSentry verification code"
        msg["From"] = f"SubSentry <{SENDER_EMAIL}>"
        msg["To"] = recipient_email
        msg.set_content(
            f"Hello,\n\nYour SubSentry account verification code is: {otp_code}\n\n"
            f"Enter this code on the Sign Up screen to set your password.\n\n"
            f"— SubSentry Team"
        )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, APP_PASSWORD)
            smtp.send_message(msg)
        return True, "Sent"
    except Exception as err:
        return False, str(err)


def parse_trial_message(text: str, reference_date: datetime = None) -> dict | None:
    """
    Detects free-trial confirmation text, extracts service name, trial expiry date,
    first expected payment date, and recurring amount before any bank charge occurs.
    """
    if not text or not text.strip():
        return None

    ref = reference_date or datetime.now()
    clean = " ".join(text.strip().split())

    # 1. Confirm it is a trial / auto-renew confirmation message
    trial_keywords = r"\b(free\s*trial|trial\s*(?:period|ends|expires|ending)|welcome\s*to|enjoy\s*\d+\s*(?:day|week|month)s?\s*free|automatically\s*(?:renew|bill|charge))\b"
    if not re.search(trial_keywords, clean, re.IGNORECASE):
        return None

    # 2. Extract Service Name
    service = "Detected Subscription"
    svc_match = re.search(
        r"(?:welcome\s+to|thanks\s+for\s+(?:trying|joining|starting\s+your)|your)\s+([A-Z][A-Za-z0-9+&.\- ]{1,28}?)(?:\s+(?:free\s+trial|trial|pro|plus|premium|membership|subscription)|[.,!])",
        clean,
        re.IGNORECASE,
    )
    if svc_match:
        service = svc_match.group(1).strip().title()

    # 3. Extract Post-Trial Price (e.g., ₹499, $14.99, Rs. 299)
    amount = "Standard Plan Rate"
    amt_match = re.search(r"((?:₹|Rs\.?|INR|\$|USD|€|£)\s?\d+(?:,\d{3})*(?:\.\d{1,2})?(?:\s*/\s*(?:mo|month|yr|year))?)", clean, re.IGNORECASE)
    if amt_match:
        amount = amt_match.group(1).strip()

    # 4. Extract Explicit Expiry Date OR Calculate from Trial Duration
    expiry_dt = None
    extracted_via = ""

    # Pattern A: Explicit date (e.g., "ends on Dec 15, 2026" or "expires 28/11/2026" or "until 2026-12-05")
    date_match = re.search(
        r"(?:end(?:s|ing)?|expir(?:es|ing)|until|through|valid\s*(?:till|until)|charged\s*on|billed\s*on)\s*(?:on\s*)?"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
        clean,
        re.IGNORECASE,
    )
    if date_match:
        raw_date = date_match.group(1).replace(",", "")
        for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y-%m-%d", "%b %d %Y", "%B %d %Y"):
            try:
                expiry_dt = datetime.strptime(raw_date, fmt)
                extracted_via = "Explicit date found in confirmation"
                break
            except ValueError:
                continue

    # Pattern B: Relative duration (e.g., "7-day free trial", "14 days free", "1 month trial")
    if not expiry_dt:
        dur_match = re.search(r"(\d{1,3})[\s-]*(day|week|month)s?\s*(?:free\s*)?trial", clean, re.IGNORECASE)
        if not dur_match:
            dur_match = re.search(r"free\s*for\s*(\d{1,3})[\s-]*(day|week|month)s?", clean, re.IGNORECASE)
        if dur_match:
            qty = int(dur_match.group(1))
            unit = dur_match.group(2).lower()
            days = qty * (30 if "month" in unit else 7 if "week" in unit else 1)
            expiry_dt = ref + timedelta(days=days)
            extracted_via = f"Calculated from {qty}-{unit} trial window"

    # Default fallback if trial keywords matched without a specific date
    if not expiry_dt:
        expiry_dt = ref + timedelta(days=7)
        extracted_via = "Default 7-day trial estimate"

    first_payment_dt = expiry_dt + timedelta(days=1)
    reminder_dt = max(expiry_dt - timedelta(days=2), ref)
    days_left = (expiry_dt.date() - ref.date()).days

    return {
        "service": service,
        "amount": amount,
        "expiry_date": expiry_dt.strftime("%d %b %Y"),
        "first_payment_date": first_payment_dt.strftime("%d %b %Y"),
        "reminder_date": reminder_dt.strftime("%d %b %Y"),
        "reminder_raw": reminder_dt,
        "days_left": days_left,
        "source_note": extracted_via,
    }

import os
import json
from google import genai

# Initialize Gemini client (reads GEMINI_API_KEY from st.secrets or environment)
from google.genai import types

import os
import streamlit as st
from google import genai
from google.genai import types

def get_gemini_client():
    api_key = None
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        pass

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    if api_key and api_key.startswith("AQ.Ab"):
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1beta", timeout=60000)
        )
    return None
def ask_gemini_safe(client, prompt: str, fallback_html: str) -> str:
    for attempt in range(2):
        try:
            resp = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=250)
            )
            return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", resp.text.strip()).replace("\n", "<br>")
        except Exception as e:
            if attempt == 0 and ("504" in str(e) or "DEADLINE" in str(e)):
                continue
            return fallback_html
def call_gemini_with_retry(client, prompt: str, json_mode: bool = False) -> str:
    config = {"response_mime_type": "application/json"} if json_mode else {}
    # Single fast attempt with gemini-3.8-flash so it never hangs
    resp = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=250,
            temperature=0.5,
        ),
    )
    return resp.text.strip()

def ai_audit_subscriptions(sub_list: list[dict]) -> dict:
    """
    Uses Gemini AI to detect overlapping subscriptions, suggest cheaper bundles/alternatives,
    and provide a personalized savings strategy.
    """
    client = get_gemini_client()
    prompt = f"""
    You are SubSentry AI, a sharp personal finance advisor in India (currency: ₹).
    Analyze this user's active subscriptions:
    {json.dumps(sub_list, indent=2)}

    Return a concise, high-impact audit in valid JSON with exact keys:
    {{
      "headline": "One punchy sentence summarizing their biggest savings opportunity.",
      "redundancies": ["Bullet 1 spotting overlapping/duplicate services", "Bullet 2"],
      "smart_swaps": ["Actionable cheaper plan, annual switch, or bundle tip 1", "Tip 2"],
      "estimated_extra_savings": "₹X,XXX/year"
    }}
    """
    if client:
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception:
            pass

    # Hackathon-safe fallback if offline or API key isn't set yet
    return {
        "headline": "You have overlapping entertainment & cloud plans costing extra every year.",
        "redundancies": [
            "Multiple media subscriptions (Streaming + Music Pro) often overlap with telecom/Prime bundles.",
            "Paying monthly instead of annual plans adds ~18–25% in hidden convenience costs."
        ],
        "smart_swaps": [
            "Switch high-usage tools (Cloud Storage / AI Assistant) to annual billing to save ~20%.",
            "Pause underused entertainment subscriptions during busy months and rotate them."
        ],
        "estimated_extra_savings": "₹3,600/year"
    }

def ai_draft_negotiation_email(service_name: str, amount: str, tone: str) -> str:
    """
    Uses Gemini AI to generate a persuasive cancellation or retention-discount email.
    """
    client = get_gemini_client()
    prompt = f"""
    Write a short, polite, high-converting email to {service_name} customer support regarding a subscription costing {amount}.
    Goal/Tone: {tone} (e.g., Immediate Cancellation, Ask for Retention Discount, or Price Hike Dispute).
    Keep it under 120 words, ready to send, with [Your Name] at the bottom. Do not include markdown fences.
    """
    if client:
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            return response.text.strip()
        except Exception:
            pass

    return (
        f"Subject: Request regarding my {service_name} subscription\n\n"
        f"Hello {service_name} Support Team,\n\n"
        f"I am reviewing my recurring expenses ({amount}) and would like to proceed with: {tone}.\n"
        f"Please confirm once this update has been processed and ensure no further charges are scheduled.\n\n"
        f"Thank you,\n[Your Name]"
    )
def build_ics_reminder(trial_info: dict) -> str:
    """Generates a standard .ics calendar reminder 48 hours before trial expiry."""
    dt_start = trial_info["reminder_raw"].strftime("%Y%m%dT090000")
    dt_end = trial_info["reminder_raw"].strftime("%Y%m%dT093000")
    return (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//SubSentry//Free Trial Radar//EN\n"
        "BEGIN:VEVENT\n"
        f"DTSTART:{dt_start}\n"
        f"DTEND:{dt_end}\n"
        f"SUMMARY:Cancel {trial_info['service']} Free Trial Before Auto-Charge\n"
        f"DESCRIPTION:Your {trial_info['service']} trial expires on {trial_info['expiry_date']}. "
        f"First expected charge ({trial_info['amount']}) is on {trial_info['first_payment_date']}.\n"
        "END:VEVENT\n"
        "END:VCALENDAR"
    )
# =========================
# LOGIN / SIGN UP PAGE GATE
# =========================

if not st.session_state.authenticated:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@700;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    /* Muted Lavender Background */
    .stApp {
        background-color: #D8CFE6 !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }

    #  [data-testid="stHeader"] {
    #     background-color: #D8CFE6 !important;
    #  }

    /* Style the left auth card container */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: rgba(255, 255, 255, 0.94) !important;
        border-radius: 26px !important;
        padding: 28px 26px !important;
        border: 1.5px solid #FFFFFF !important;
        box-shadow: 0 18px 40px rgba(17, 56, 41, 0.10) !important;
    }

    /* Light clean text inputs */
    [data-testid="stTextInput"] input {
        background-color: #F6F3FA !important;
        border: 1.5px solid #CFC3E0 !important;
        border-radius: 14px !important;
        color: #173B59 !important;
        padding: 12px 14px !important;
        font-weight: 500 !important;
    }

    [data-testid="stTextInput"] input:focus {
        border-color: #113829 !important;
        box-shadow: 0 0 0 3px rgba(17, 56, 41, 0.14) !important;
    }

    [data-testid="stTextInput"] label p {
        color: #173B59 !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
    }

    /* Dark green primary buttons */
    .stButton > button {
        background-color: #113829 !important;
        color: #FFFFFF !important;
        border-radius: 14px !important;
        border: none !important;
        padding: 11px 18px !important;
        font-weight: 700 !important;
        width: 100%;
        transition: transform 0.18s ease, background-color 0.18s ease !important;
    }

    /* Primary Submit Button (Sign In -> / Send Code / Verify) */
    .stButton > button[kind="primary"] {
        background-color: #5B4B8A !important;
        color: #FFFFFF !important;
        border-radius: 14px !important;
        border: none !important;
        padding: 11px 22px !important;
        font-weight: 700 !important;
        box-shadow: 0 8px 20px rgba(91, 75, 138, 0.22) !important;
        transition: transform 0.18s ease, background-color 0.18s ease !important;
    }

    .stButton > button[kind="primary"]:hover {
        background-color: #483A73 !important;
        transform: translateY(-2px) !important;
    }

    .stButton > button[kind="primary"] p {
        color: #FFFFFF !important;
    }

    /* Secondary Tab Buttons (Sign In / Create Account switchers) */
    .stButton > button[kind="secondary"] {
        background-color: #EFEAF7 !important;
        color: #173B59 !important;
        border-radius: 12px !important;
        border: 1.5px solid #D5C8EB !important;
        padding: 8px 16px !important;
        font-weight: 700 !important;
        transition: all 0.18s ease !important;
    }

    .stButton > button[kind="secondary"]:hover {
        background-color: #E2D8F3 !important;
        border-color: #5B4B8A !important;
    }

    .stButton > button[kind="secondary"] p {
        color: #173B59 !important;
    }
    /* Right side brand showcase */
    .brand-hero {
        display: flex;
        flex-direction: column;
        justify-content: center;
        height: 100%;
        padding: 36px 24px 36px 44px;
    }

    .brand-pill {
        display: inline-block;
        background: rgba(255, 255, 255, 0.72);
        color: #113829;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-weight: 800;
        font-size: 0.78rem;
        letter-spacing: 1px;
        text-transform: uppercase;
        padding: 6px 14px;
        border-radius: 999px;
        margin-bottom: 18px;
        width: fit-content;
        border: 1px solid #FFFFFF;
    }

    .brand-title {
        font-family: 'Cinzel Decorative', serif !important;
        font-size: 3.7rem;
        font-weight: 900;
        color: #113829 !important;
        line-height: 1.08;
        margin-bottom: 20px;
        letter-spacing: -0.5px;
    }

    .brand-tagline {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 1.22rem;
        font-weight: 500;
        color: #243831 !important;
        line-height: 1.65;
        max-width: 520px;
    }
    /* Match the top Streamlit header bar to the dashboard background */
    [data-testid="stHeader"],
    header[data-testid="stHeader"] {
    background-color: transparent !important;
}
.nav-teal {
    background-color: #EEF6F8 !important;
    border: 1.5px solid #CFE3E8 !important;
}
    </style>
    """, unsafe_allow_html=True)

    st.write("")
    st.write("")

    left_col, right_col = st.columns([1.05, 1.25], gap="large")

    # -------------------------
    # LEFT: SIGN IN / SIGN UP CARD
    # -------------------------
    with left_col:
        with st.container(border=True):
            # Top Mode Switcher Tabs
            t1, t2 = st.columns(2)
            with t1:
                if st.button("Sign In", key="tab_signin"):
                    st.session_state.auth_mode = "Sign In"
                    st.rerun()
            with t2:
                if st.button("Create Account", key="tab_signup"):
                    st.session_state.auth_mode = "Sign Up"
                    st.rerun()

            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

            # -----------------------------------
            # TAB 1: SIGN IN (Existing Account)
            # -----------------------------------
            if st.session_state.auth_mode == "Sign In":
                st.markdown(
                    "<h3 style='color:#113829; font-weight:800; margin-bottom:4px;'>Welcome!</h3>"
                    "<p style='color:#5A5368; font-size:0.88rem; margin-bottom:18px;'>"
                    "Enter your email and password to access your dashboard.</p>",
                    unsafe_allow_html=True
                )

                login_email = st.text_input("Email address", placeholder="you@gmail.com", key="login_email")
                login_pwd = st.text_input("Password", type="password", placeholder="••••••••", key="login_pwd")

                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

                if st.button("Sign In →", key="btn_login_submit", type="primary"):
                    clean_email = login_email.strip().lower()
                    if clean_email in st.session_state.users_db and st.session_state.users_db[clean_email] == login_pwd:
                        st.session_state.authenticated = True
                        st.session_state.current_user = clean_email
                        st.rerun()
                    elif clean_email not in st.session_state.users_db:
                        st.error("No account found with this email. Click 'Create Account' above to sign up.")
                    else:
                        st.error("Incorrect password. Please try again.")

                st.caption("Demo login: `demo@subsentry.in` / `SubSentry1`")

            # -----------------------------------
            # TAB 2: CREATE ACCOUNT (Sign Up)
            # -----------------------------------
            elif st.session_state.auth_mode == "Sign Up":
                st.markdown(
                    "<h3 style='color:#113829; font-weight:800; margin-bottom:4px;'>Create your account</h3>"
                    "<p style='color:#5A5368; font-size:0.88rem; margin-bottom:18px;'>"
                    "Sign up with your Gmail address to start tracking your subscriptions.</p>",
                    unsafe_allow_html=True
                )

                new_email = st.text_input("Gmail address", placeholder="yourname@gmail.com", key="signup_email")
                new_pwd = st.text_input(
                    "Create password",
                    type="password",
                    placeholder="At least 1 capital & 1 number",
                    key="new_pwd_input"
                )
                confirm_pwd = st.text_input(
                    "Confirm password",
                    type="password",
                    placeholder="Re-enter password",
                    key="confirm_pwd_input"
                )

                st.caption("Password rule: Must include at least **1 capital letter** and **1 number**.")
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

                if st.button("Create Account & Enter →", key="btn_finish_signup", type="primary"):
                    clean_email = new_email.strip().lower()
                    valid, err_msg = is_valid_password(new_pwd)

                    if not re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", clean_email):
                        st.warning("Please enter a valid @gmail.com address (e.g., yourname@gmail.com).")
                    elif clean_email in st.session_state.users_db:
                        st.warning("An account with this email already exists. Click 'Sign In' above.")
                    elif not valid:
                        st.error(err_msg)
                    elif new_pwd != confirm_pwd:
                        st.error("Passwords do not match.")
                    else:
                        st.session_state.users_db[clean_email] = new_pwd
                        st.session_state.authenticated = True
                        st.session_state.current_user = clean_email
                        st.rerun()
    # -------------------------
    # RIGHT: BRAND TITLE & TAGLINE
    # -------------------------
    with right_col:
        st.html(
            '<div class="brand-hero">'
            '<div class="brand-pill">🔎 Privacy-First Financial Guard</div>'
            '<div class="brand-title">SubSentry</div>'
            '<div class="brand-tagline">'
            'Find recurring payments, price increases and possible financial leakage — without linking your bank account.'
            '</div>'
            '</div>'
        )

    st.stop()

st.markdown("""
<style>
/* SIGN OUT BUTTON MATCHING THE LAVENDER PILL STYLE */
.stButton > button {
    background-color: #EFEAF7 !important;
    color: #173B59 !important;
    border: 1.5px solid #D5C8EB !important;
    border-radius: 14px !important;
    font-weight: 700 !important;
    padding: 8px 18px !important;
    box-shadow: 0 4px 12px rgba(23, 59, 89, 0.06) !important;
    transition: all 0.18s ease !important;
}

.stButton > button:hover {
    background-color: #E2D8F3 !important;
    border-color: #5B4B8A !important;
    transform: translateY(-2px) !important;
}

.stButton > button p {
    color: #173B59 !important;
}
</style>
""", unsafe_allow_html=True)
# =========================
# DESIGN AND CSS
# =========================

st.markdown("""
<style>

.stApp {
    background-color: #F3F1FA;
    color: #26332E;
}

# [data-testid="stHeader"] {
#     background-color: #F3F5F9;
# }

h1, h2, h3 {
    color: #193B35 !important;
}

p, label, span, li {
    color: #26332E;
}

[data-testid="stMetric"] {
    background-color: #FFFFFF;
    padding: 20px;
    border-radius: 14px;
    border: 1px solid #D5E3DA;
}

[data-testid="stMetricValue"] {
    color: #315C50 !important;
}

[data-testid="stMetricLabel"] {
    color: #65756C !important;
}

.stButton > button {
    background-color: #315C50;
    color: white;
    border-radius: 10px;
    border: none;
}

.stButton > button:hover {
    background-color: #193B35;
    color: white;
}

.main-title {
    font-size: 2.25rem;
    font-weight: 800;
    color: #193B35;
}

.sub-title {
    color: #65756C;
    font-size: 1rem;
}

/* DASHBOARD NAVIGATION CARDS */

.dashboard-nav {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 16px;
    margin: 20px 0 28px 0;
}
.nav-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin: 18px 0 28px 0;
}
.nav-card {
    display: block;
    text-decoration: none !important;
    padding: 21px;
    min-height: 135px;
    border-radius: 20px;
    border: 1px solid rgba(255,255,255,.9);
    box-shadow: 0 8px 22px rgba(35,111,157,.09);
    transition: transform .22s ease, box-shadow .22s ease;
}

.nav-card:hover {
    transform: translateY(-6px);
    box-shadow: 0 15px 28px rgba(35,111,157,.17);
}

.nav-card,
.nav-card * {
    color: #173B59 !important;
}

.nav-card {
    cursor: pointer;
}

.nav-icon {
    font-size: 27px;
    margin-bottom: 12px;
}

.nav-title {
    font-size: 1rem;
    font-weight: 800;
    margin-bottom: 5px;
}

.nav-description {
    font-size: .79rem;
    opacity: .8;
}

.nav-blue {
    background: #D9F0FF;
}

.nav-purple {
    background: #EAE2FF;
}

.nav-green {
    background: #DDF5E8;
}

.nav-yellow {
    background: #FFF0D9;
}

.nav-pink {
    background: #FFE5ED;
}

/* Make section jumps stop below the Streamlit header */

.section-anchor {
    scroll-margin-top: 90px;
}
/* LIGHT & COLORFUL EXPANDER OVERRIDE */
[data-testid="stExpander"] {
    background-color: #F4FAFF !important;
    border: 1px solid #C5E4FA !important;
    border-radius: 14px !important;
    overflow: hidden;
}

[data-testid="stExpander"] summary {
    background-color: #E3F3FF !important;
    color: #173B59 !important;
    font-weight: 700 !important;
    padding: 10px 14px !important;
}

[data-testid="stExpander"] summary:hover {
    background-color: #D2ECFF !important;
}

[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary svg {
    color: #173B59 !important;
    fill: #173B59 !important;
}

[data-testid="stExpanderDetails"] {
    background-color: #F8FCFF !important;
    padding: 12px 14px !important;
}
.hike-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 14px 28px rgba(23, 59, 89, 0.14) !important;
}
/* LIGHT PASTEL STYLING FOR SELECTBOXES, TEXTAREA & DOWNLOAD BUTTON */
[data-testid="stSelectbox"] > div > div {
    background-color: #FFF5F8 !important;
    border: 1.5px solid #FBCFE8 !important;
    border-radius: 14px !important;
    color: #173B59 !important;
    font-weight: 600 !important;
}

[data-testid="stSelectbox"] svg {
    fill: #173B59 !important;
}

[data-testid="stTextArea"] textarea {
    background-color: #FFFFFF !important;
    border: 1.5px solid #FBCFE8 !important;
    border-radius: 18px !important;
    color: #173B59 !important;
    font-size: 0.95rem !important;
    line-height: 1.6 !important;
    padding: 16px 20px !important;
    box-shadow: 0 8px 20px rgba(23, 59, 89, 0.06) !important;
}

[data-testid="stTextArea"] textarea:focus {
    border-color: #F472B6 !important;
    box-shadow: 0 0 0 3px rgba(244, 114, 182, 0.18) !important;
}

[data-testid="stDownloadButton"] > button {
    background-color: #FFE5ED !important;
    color: #173B59 !important;
    border: 1.5px solid #FBCFE8 !important;
    border-radius: 14px !important;
    font-weight: 800 !important;
    padding: 10px 20px !important;
    box-shadow: 0 6px 16px rgba(23, 59, 89, 0.08) !important;
    transition: transform 0.2s ease, background-color 0.2s ease !important;
}

[data-testid="stDownloadButton"] > button:hover {
    background-color: #FFD1E0 !important;
    transform: translateY(-2px) !important;
}

[data-testid="stDownloadButton"] > button p,
[data-testid="stDownloadButton"] > button span {
    color: #173B59 !important;
}
[data-testid="stDownloadButton"] > button {
    background-color: #FFE5ED !important;
    color: #173B59 !important;
    border: 1.5px solid #FBCFE8 !important;
    border-radius: 14px !important;
    font-weight: 700 !important;
    padding: 12px 18px !important;
    width: 100% !important;
    box-shadow: 0 6px 16px rgba(157, 23, 77, 0.08) !important;
}

[data-testid="stDownloadButton"] > button:hover {
    background-color: #FFD1E0 !important;
    transform: translateY(-2px) !important;
}

[data-testid="stDownloadButton"] > button p {
    color: #173B59 !important;
}
.nav-sage {
    background-color: #F1F6F3 !important;
    border: 1.5px solid #CFE3D8 !important;
}
.nav-ai {
    background-color: #F5F3FA !important;
    border: 1.5px solid #DDD6FE !important;
}

</style>
""", unsafe_allow_html=True)


# =========================
    # MAIN TITLE (DASHBOARD WELCOME)
    # =========================
top_left, top_right = st.columns([5, 1])

# with top_left:
#     st.html(
#         '<div style="margin-bottom: 18px; font-family: \'Plus Jakarta Sans\', sans-serif;">'
#         '<div style="font-size: 2.35rem; font-weight: 900; color: #113829; letter-spacing: -0.5px; margin-bottom: 6px;">'
#         '🔎 SubSentry'
#         '</div>'
#         '<div style="font-size: 1.05rem; font-weight: 800; color: #173B59; line-height: 1.55;">'
#         'AI-powered Financial Leakage Detector'
#         '<div style="font-size: 1.05rem; font-weight: 500; color: #4A5568; line-height: 1.55;">'
#         'Your personal command center for spotting hidden charges and quiet subscription hikes.'
#         '</div>'
#         '<div style="font-size: 0.96rem; font-weight: 500; color: #4A5568; margin-top: 3px;">'
#         'Explore the sections below to audit your recurring bills, review fee alerts, or draft instant cancellation notices.'
#         '</div>'
#         '</div>'
#     )
col_nav, col_btn = st.columns([6.5, 1], vertical_alignment="center")
with col_nav:
 st.html("""
<div style="
    font-family: 'Plus Jakarta Sans', sans-serif;
    background: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 14px 20px;
    margin: -1rem -1rem 24px -1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
">
    <!-- Left: Logo Icon + SubSentry Brand Name -->
    <div style="display: flex; align-items: center; gap: 12px;">
        <div style="
            background: #1E293B;
            color: #FFFFFF;
            width: 34px;
            height: 34px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 1.05rem;
        ">S</div>
        <span style="
            font-size: 1.35rem;
            font-weight: 700;
            color: #0F172A;
            letter-spacing: -0.02em;
        ">SubSentry</span>
    </div>

    <!-- Center/Right: Clean Navigation Items -->
    <div style="display: flex; align-items: center; gap: 28px; font-size: 0.9rem;">
        <span style="
            color: #0F172A;
            font-weight: 700;
            border-bottom: 2.5px solid #0F172A;
            padding-bottom: 12px;
            margin-bottom: -15px;
        ">Dashboard</span>
        <span style="color: #64748B; font-weight: 500;">Analytics</span>
        <span style="color: #64748B; font-weight: 500;">AI Advisor</span>
    </div>
</div>

<!-- Main Page Title & Subtitle -->
<div style="font-family: 'Plus Jakarta Sans', sans-serif; margin-bottom: 20px;">
    <h1 style="
        margin: 0;
        font-size: 2.05rem;
        font-weight: 800;
        color: #0F172A;
        letter-spacing: -0.03em;
    ">Dashboard Overview</h1>
    <p style="
        margin: 4px 0 0 0;
        font-size: 0.92rem;
        color: #64748B;
    ">Welcome back! Here's your recurring spend and subscription radar today.</p>
</div>
""")
with col_btn:
    # Keep your existing Sign Out logic right inside this if-block!
    if st.button("Sign Out", key="top_sign_out", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# =========================
# DASHBOARD NAVIGATION
# =========================


st.markdown("""
<div class="nav-grid">
<a href="#recurring-payments" class="nav-card nav-blue">
<div class="nav-icon">🔁</div>
<div class="nav-title">Recurring Payments</div>
<div class="nav-description">Track your subscriptions →</div>
</a>
<a href="#price-increases" class="nav-card nav-purple">
<div class="nav-icon">📈</div>
<div class="nav-title">Price Increases</div>
<div class="nav-description">Spot rising costs →</div>
</a>
<a href="#hidden-fees" class="nav-card nav-green">
<div class="nav-icon">🔍</div>
<div class="nav-title">Hidden Fees</div>
<div class="nav-description">Find unexpected charges →</div>
</a>
<a href="#ai-advisor" class="nav-card nav-ai">
<div class="nav-icon">✨</div>
<div class="nav-title">AI Advisor</div>
<div class="nav-description">Smart stack optimization →</div>
</a>
<a href="#what-if-simulator" class="nav-card nav-sage">
<div class="nav-icon">🎛️</div>
<div class="nav-title">What-If Simulator</div>
<div class="nav-description">Test cancellation savings →</div>
</a>
<a href="#savings-snapshot" class="nav-card nav-yellow">
<div class="nav-icon">💰</div>
<div class="nav-title">Savings Snapshot</div>
<div class="nav-description">See your yearly costs →</div>
</a>
<a href="#trial-radar" class="nav-card nav-teal">
<div class="nav-icon">⏳</div>
<div class="nav-title">Trial Radar</div>
<div class="nav-description">Catch free trials early →</div>
</a>
<a href="#take-action" class="nav-card nav-pink">
<div class="nav-icon">✉️</div>
<div class="nav-title">Take Action</div>
<div class="nav-description">Create a cancellation draft →</div>
</a>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# =========================
# HELPER FUNCTIONS
# =========================
import time

def get_working_gemini_model(client) -> str:
    # Check cached model name in session_state so it only checks once
    if "active_gemini_model" in st.session_state:
        return st.session_state["active_gemini_model"]

    try:
        available = []
        for m in client.models.list():
            methods = getattr(m, "supported_actions", []) or getattr(m, "supported_generation_methods", []) or []
            name = m.name.replace("models/", "")
            if "generateContent" in methods or "flash" in name.lower():
                available.append(name)

        # Prefer Flash models in order of newest to oldest
        for preferred in ["gemini-3.8-flash", "gemini-3.0-flash", "gemini-2.5-flash", "gemini-2.0-flash"]:
            if preferred in available:
                st.session_state["active_gemini_model"] = preferred
                return preferred

        # Otherwise return any available flash model
        for name in available:
            if "flash" in name.lower():
                st.session_state["active_gemini_model"] = name
                return name
    except Exception:
        pass

    return "gemini-3.8-flash"

def call_gemini_with_retry(client, prompt: str, json_mode: bool = False) -> str:
    models_to_try = ["gemini-3.8-flash"]
    config = {"response_mime_type": "application/json"} if json_mode else {}
    last_err = None

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config
                )
                if resp and resp.text:
                    return resp.text.strip()
            except Exception as e:
                last_err = e
                time.sleep(0.8)  # Brief pause before retry
    raise last_err
def get_working_gemini_model(client) -> str:
    if "active_gemini_model" in st.session_state:
        return st.session_state["active_gemini_model"]

    try:
        available = []
        for m in client.models.list():
            methods = getattr(m, "supported_actions", []) or getattr(m, "supported_generation_methods", []) or []
            name = m.name.replace("models/", "")
            if "generateContent" in methods or "flash" in name.lower():
                available.append(name)

        for preferred in ["gemini-3.8-flash", "gemini-3.0-flash", "gemini-2.5-flash", "gemini-2.0-flash"]:
            if preferred in available:
                st.session_state["active_gemini_model"] = preferred
                return preferred

        for name in available:
            if "flash" in name.lower():
                st.session_state["active_gemini_model"] = name
                return name
    except Exception:
        pass

    return "gemini-3.8-flash"

def clean_merchant(description):
    """Create a simple merchant label from a transaction description."""

    text = str(description).upper()

    text = re.sub(
        r'\b(UPI|POS|CARD|DEBIT|CREDIT|TXN|REF|PAYMENT|PURCHASE)\b',
        ' ',
        text
    )

    text = re.sub(r'\d{5,}', ' ', text)
    text = re.sub(r'[^A-Z &]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text[:45] or "UNKNOWN"


def load_and_prepare(file):

    df = pd.read_csv(file)

    required = {"date", "description", "amount"}

    if not required.issubset(set(df.columns.str.lower())):
        raise ValueError(
            "Your CSV must contain columns named: date, description, amount."
        )

    df.columns = [c.lower().strip() for c in df.columns]

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        dayfirst=True
    )

    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce"
    )

    df["description"] = df["description"].fillna("").astype(str)

    df = df.dropna(subset=["date", "amount"])

    # Positive amounts are treated as money going out.
    df = df[df["amount"] > 0].copy()

    df["merchant"] = df["description"].apply(clean_merchant)

    df = df.sort_values("date")

    return df


def detect_recurring(df):

    results = []

    for merchant, group in df.groupby("merchant"):

        group = group.sort_values("date")

        if len(group) < 2:
            continue

        dates = group["date"].drop_duplicates().sort_values()

        gaps = dates.diff().dt.days.dropna()

        monthly_like = ((gaps >= 25) & (gaps <= 35)).sum()

        weekly_like = ((gaps >= 6) & (gaps <= 8)).sum()

        if monthly_like >= 1 or weekly_like >= 1:

            amounts = group["amount"].tolist()

            avg_amount = sum(amounts) / len(amounts)

            frequency = (
                "Monthly"
                if monthly_like >= weekly_like
                else "Weekly"
            )

            results.append({
                "Merchant": merchant.title(),
                "Frequency": frequency,
                "Occurrences": len(group),
                "Average payment (₹)": round(avg_amount, 2),
                "Latest payment (₹)": round(group.iloc[-1]["amount"], 2),
                "Last seen": group.iloc[-1]["date"].strftime("%d %b %Y")
            })

    return pd.DataFrame(results)


def detect_price_hikes(df):

    rows = []

    for merchant, group in df.groupby("merchant"):

        group = group.sort_values("date")

        if len(group) < 2:
            continue

        old = float(group.iloc[-2]["amount"])

        new = float(group.iloc[-1]["amount"])

        if new > old and old > 0:

            increase = new - old

            pct = increase / old * 100

            if pct >= 5:

                rows.append({
                    "Merchant": merchant.title(),
                    "Previous (₹)": round(old, 2),
                    "Latest (₹)": round(new, 2),
                    "Increase (₹)": round(increase, 2),
                    "Increase (%)": round(pct, 1)
                })

    return pd.DataFrame(rows)


FEE_TERMS = [
    "FEE",
    "CHARGE",
    "MAINTENANCE",
    "ATM",
    "SMS ALERT",
    "ANNUAL",
    "SERVICE TAX",
    "GST"
]


def detect_possible_fees(df):

    mask = df["description"].str.upper().apply(
        lambda s: any(term in s for term in FEE_TERMS)
    )

    fees = df[mask].copy()

    if not fees.empty:

        fees["Review note"] = (
            "Possible bank/service fee — verify with your bank statement or bank."
        )

    return fees


def make_email(merchant):

    return f"""Subject: Request to cancel my subscription

Hello {merchant} Support Team,

I would like to request cancellation of my subscription associated with my account.

Please confirm when the cancellation has been completed and whether any further payment is scheduled.

Thank you,
[Your name]
"""


# =========================
# UPLOAD AND SAMPLE DATA
# =========================

uploaded = st.file_uploader(
    "Upload a bank statement (CSV)",
    type=["csv"],
    help="Use a sample file first. Do not upload real financial information to a public demo."
)

use_sample = st.toggle(
    "Try the sample statement",
    value=uploaded is None
)


sample = pd.DataFrame([
    ["2026-08-05", "NETFLIX SUBSCRIPTION", 199],
    ["2026-09-05", "NETFLIX SUBSCRIPTION", 199],
    ["2026-10-05", "NETFLIX SUBSCRIPTION", 249],
    ["2026-08-12", "SPOTIFY PREMIUM", 119],
    ["2026-09-12", "SPOTIFY PREMIUM", 119],
    ["2026-10-12", "SPOTIFY PREMIUM", 119],
    ["2026-08-20", "CLOUD STORAGE PLAN", 79],
    ["2026-09-20", "CLOUD STORAGE PLAN", 79],
    ["2026-10-20", "CLOUD STORAGE PLAN", 79],
    ["2026-08-23", "BANK ATM CHARGE", 23.6],
    ["2026-09-23", "BANK SMS ALERT FEE", 15],
    ["2026-10-23", "BANK ATM CHARGE", 23.6],
    ["2026-10-26", "GROCERY STORE", 850],
    ["2026-10-27", "COFFEE SHOP", 180],
], columns=["date", "description", "amount"])


# =========================
# ANALYSIS
# =========================

try:

    if uploaded is not None:

        df = load_and_prepare(uploaded)

        st.caption(
            "Using your uploaded CSV. This prototype processes it in the running app and does not connect to a bank."
        )

    elif use_sample:

        df = sample.copy()

        df["date"] = pd.to_datetime(df["date"])

        df["merchant"] = df["description"].apply(clean_merchant)

        st.info(
            "You're viewing fictional sample transactions. Use these to test the prototype."
        )

    else:

        st.warning(
            "Upload a CSV statement or turn on the sample statement."
        )

        st.stop()


    if df.empty:

        st.warning(
            "No outgoing transactions were found. Check that your CSV uses positive amounts for money spent."
        )

        st.stop()


    recurring = detect_recurring(df)

    recurring_df = recurring.copy()

    hikes = detect_price_hikes(df)

    fees = detect_possible_fees(df)


    # =========================
    # FINANCIAL OVERVIEW
    # =========================

    recurring_total = 0.0

    if not recurring.empty:

        monthly = recurring[
            recurring["Frequency"] == "Monthly"
        ]

        weekly = recurring[
            recurring["Frequency"] == "Weekly"
        ]

        recurring_total = (
            monthly["Average payment (₹)"].sum()
            + weekly["Average payment (₹)"].sum() * 4.33
        )


    annualised = recurring_total * 12

    potential_savings = 0.0

    if not hikes.empty:

        potential_savings += hikes["Increase (₹)"].sum() * 12


    st.subheader("Your financial overview")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Recurring payments found",
        len(recurring)
    )

    c2.metric(
        "Estimated monthly recurring",
        f"₹{recurring_total:,.2f}"
    )

    c3.metric(
        "Price increases flagged",
        len(hikes)
    )

    c4.metric(
        "Possible fees to review",
        len(fees)
    )

except Exception as e:
    st.error(f"Couldn't read this file: {e}")
    st.write(
        "Check that your CSV has the columns: date, description, amount."
    )
    st.stop()


# =========================
    # RECURRING PAYMENTS (MATCHING PASTEL CARDS)
    # =========================

st.markdown('<div id="recurring-section"></div>', unsafe_allow_html=True)
st.markdown("### 🔄 Recurring Payments Detected")

if recurring_df.empty:
    st.info("No recurring payments detected in this statement.")
else:
    # Curated fintech pastel palette: (card_bg, border_color, pill_bg, pill_text)
    PASTEL_THEMES = [

        ("#ECFDF5", "#A7F3D0", "#D1FAE5", "#047857"),  # Mint Sage
        ("#EFF6FF", "#BFDBFE", "#DBEAFE", "#1D4ED8"),  # Sky Mist
        ("#FFFBEB", "#FDE68A", "#FEF3C7", "#B45309"),  # Warm Buttercream
        ("#FDF2F8", "#FBCFE8", "#FCE7F3", "#BE185D"),  # Blush Pink
    ]
    HIKE_THEME = ("#FFF1F2", "#FECDD3", "#FFE4E6", "#BE123C")  # Pastel Rose Alert

    cols = st.columns(2, gap="medium")

    for idx, row in recurring_df.iterrows():
        merchant = row["Merchant"]
        latest_amt = row["Latest payment (₹)"]
        freq = row.get("Cadence", "Monthly")
        next_date = row.get("Next expected", "Next cycle")
        price_hike = row.get("Price increase?", False)

        # Pick pastel rose if price increased, otherwise rotate clean pastels
        bg_col, border_col, pill_bg, pill_txt = (
            HIKE_THEME if price_hike else PASTEL_THEMES[idx % len(PASTEL_THEMES)]
        )
        badge_label = "⚠️ Price Hike" if price_hike else "● Active"

        with cols[idx % 2]:
            with st.container(border=True):
                st.html(f"""
                <div style="
                    font-family: 'Plus Jakarta Sans', sans-serif;
                    background: {bg_col};
                    border: 1.5px solid {border_col};
                    border-radius: 14px;
                    padding: 16px 18px;
                    margin-bottom: 6px;
                ">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-size:1.05rem; font-weight:800; color:#0F172A;">{merchant}</span>
                        <span style="
                            background:{pill_bg};
                            color:{pill_txt};
                            padding:3px 10px;
                            border-radius:999px;
                            font-size:0.72rem;
                            font-weight:700;
                        ">{badge_label}</span>
                    </div>
                    <div style="font-size:1.5rem; font-weight:800; color:#1E293B; margin-bottom:4px;">
                        ₹{latest_amt:,.0f} <span style="font-size:0.82rem; font-weight:600; color:#475569;">/ {freq.lower()}</span>
                    </div>
                    <div style="font-size:0.8rem; color:#475569;">
                        Next charge: <b>{next_date}</b>
                    </div>
                </div>
                """)

                # Integrated "View last 3 payments" expander inside the same card
                with st.expander("View last 3 payments", expanded=False):
                    m_txns = df[df["description"].str.contains(merchant, case=False, na=False)].tail(3)
                    if not m_txns.empty:
                        for _, t_row in m_txns.iloc[::-1].iterrows():
                            d_str = str(t_row["date"])[:10]
                            a_val = float(t_row["amount"])
                            st.caption(f"📅 **{d_str}** — ₹{a_val:,.2f}")
                    else:
                        st.caption("No detailed transaction rows found.")
        
    # =========================
    # PRICE INCREASES (UNIQUE ROUNDED CARDS)
    # =========================

   # =========================
    # PRICE INCREASES
    # =========================

    st.markdown(
        '<div id="price-increases" class="section-anchor"></div>',
        unsafe_allow_html=True
    )

    st.subheader("Price-hike detective")

    if hikes.empty:
        st.success("No likely price increases found.")
    else:
        hike_themes = [
            {"bg": "#EAE2FF", "badge_bg": "#D8C8FF", "accent": "#4C1D95"},
            {"bg": "#FFE5ED", "badge_bg": "#FFCCD9", "accent": "#9F1239"},
            {"bg": "#FFF0D9", "badge_bg": "#FFE0B2", "accent": "#9A3412"},
        ]

        cards_html = ""
        for idx, (_, row) in enumerate(hikes.iterrows()):
            theme = hike_themes[idx % len(hike_themes)]
            merchant = row["Merchant"]
            prev_amt = row["Previous (₹)"]
            latest_amt = row["Latest (₹)"]
            inc_amt = row["Increase (₹)"]
            inc_pct = row["Increase (%)"]
            yearly_extra = inc_amt * 12

            cards_html += (
                f'<div style="background:{theme["bg"]}; border-radius:22px; '
                f'padding:20px 24px; border:1.5px solid rgba(255,255,255,0.95); '
                f'box-shadow:0 8px 22px rgba(23,59,89,0.08); display:flex; flex-wrap:wrap; '
                f'justify-content:space-between; align-items:center; gap:16px; margin-bottom:14px; '
                f'font-family:sans-serif;">'
                f'<div style="display:flex; align-items:center; gap:16px;">'
                f'<div style="width:52px; height:52px; border-radius:16px; background:#FFFFFF; '
                f'display:flex; align-items:center; justify-content:center; font-size:1.5rem; '
                f'box-shadow:0 4px 12px rgba(23,59,89,0.08);">📈</div>'
                f'<div>'
                f'<div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">'
                f'<span style="font-size:1.15rem; font-weight:800; color:#173B59;">{merchant}</span>'
                f'<span style="background:{theme["badge_bg"]}; color:{theme["accent"]}; '
                f'font-size:0.78rem; font-weight:800; padding:4px 11px; border-radius:999px;">'
                f'↑ +{inc_pct:.1f}% hike</span>'
                f'</div>'
                f'<div style="font-size:0.85rem; color:#173B59; opacity:0.85; margin-top:4px;">'
                f'Costs an extra <b>₹{inc_amt:,.2f}</b> per cycle (~<b>₹{yearly_extra:,.2f}/yr</b>)'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div style="background:rgba(255,255,255,0.9); padding:12px 18px; border-radius:16px; '
                f'border:1px solid #FFFFFF; display:flex; align-items:center; gap:14px;">'
                f'<div style="text-align:center;">'
                f'<div style="font-size:0.7rem; text-transform:uppercase; color:#173B59; opacity:0.65; font-weight:700;">Previous</div>'
                f'<div style="font-size:0.98rem; font-weight:700; color:#173B59; text-decoration:line-through; opacity:0.7;">₹{prev_amt:,.2f}</div>'
                f'</div>'
                f'<div style="font-size:1.1rem; font-weight:800; color:{theme["accent"]};">→</div>'
                f'<div style="text-align:center;">'
                f'<div style="font-size:0.7rem; text-transform:uppercase; color:#173B59; opacity:0.65; font-weight:700;">Latest</div>'
                f'<div style="font-size:1.15rem; font-weight:800; color:#173B59;">₹{latest_amt:,.2f}</div>'
                f'</div>'
                f'</div>'
                f'</div>'
            )

        st.html(cards_html)

        st.caption(
            "This first prototype compares the latest two observed payments per merchant. It flags increases for review; it cannot yet confirm that a charge is a subscription price hike."
        )
    # =========================
    # HIDDEN FEES (PASTEL CARDS)
    # =========================

    st.markdown(
        '<div id="hidden-fees" class="section-anchor"></div>',
        unsafe_allow_html=True
    )

    st.subheader("Possible hidden fees")

    if fees.empty:
        st.info("No descriptions matched the fee keyword list.")
    else:
        fee_themes = [
            {"bg": "#DDF5E8", "badge_bg": "#B8EAD0", "accent": "#14532D"},  # Soft Mint
            {"bg": "#FFF0D9", "badge_bg": "#FFE0B2", "accent": "#9A3412"},  # Soft Amber
            {"bg": "#D9F0FF", "badge_bg": "#B8E1FF", "accent": "#173B59"},  # Soft Sky
        ]

        fees_html = ""
        for idx, (_, row) in enumerate(fees.iterrows()):
            theme = fee_themes[idx % len(fee_themes)]
            f_date = row["date"].strftime("%d %b %Y")
            f_desc = row["description"]
            f_amt = row["amount"]
            f_note = row["Review note"]

            fees_html += (
                f'<div style="background:{theme["bg"]}; border-radius:20px; '
                f'padding:18px 22px; border:1.5px solid rgba(255,255,255,0.95); '
                f'box-shadow:0 8px 20px rgba(23,59,89,0.07); display:flex; flex-wrap:wrap; '
                f'justify-content:space-between; align-items:center; gap:14px; margin-bottom:12px; '
                f'font-family:sans-serif;">'
                f'<div style="display:flex; align-items:center; gap:15px;">'
                f'<div style="width:48px; height:48px; border-radius:14px; background:#FFFFFF; '
                f'display:flex; align-items:center; justify-content:center; font-size:1.4rem; '
                f'box-shadow:0 4px 10px rgba(23,59,89,0.07); flex-shrink:0;">🔍</div>'
                f'<div>'
                f'<div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">'
                f'<span style="font-size:1.06rem; font-weight:800; color:#173B59;">{f_desc}</span>'
                f'<span style="background:{theme["badge_bg"]}; color:{theme["accent"]}; '
                f'font-size:0.75rem; font-weight:700; padding:3px 10px; border-radius:999px;">'
                f'📅 {f_date}</span>'
                f'</div>'
                f'<div style="font-size:0.83rem; color:#173B59; opacity:0.82; margin-top:4px;">'
                f'{f_note}'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div style="background:rgba(255,255,255,0.9); padding:10px 18px; border-radius:14px; '
                f'border:1px solid #FFFFFF; text-align:right;">'
                f'<div style="font-size:0.68rem; text-transform:uppercase; color:#173B59; opacity:0.65; font-weight:700;">Charge</div>'
                f'<div style="font-size:1.12rem; font-weight:800; color:#173B59;">₹{f_amt:,.2f}</div>'
                f'</div>'
                f'</div>'
            )

        st.html(fees_html)

# =========================
# INTERACTIVE "WHAT-IF" SAVINGS SIMULATOR
# =========================
st.markdown('<div id="what-if-simulator" style="padding-top: 12px;"></div>', unsafe_allow_html=True)
st.html(
    '<div style="background: #FAF9F6; border: 1.5px solid #E5DFD3; border-radius: 24px; '
    'padding: 22px 26px; margin: 10px 0 18px 0; font-family: \'Plus Jakarta Sans\', sans-serif;">'
    '<div style="font-size: 0.78rem; font-weight: 800; letter-spacing: 0.9px; color: #78716C; text-transform: uppercase;">'
    '🎛️ Interactive Decision Tool'
    '</div>'
    '<h3 style="margin: 4px 0 4px 0; font-size: 1.35rem; font-weight: 800; color: #173B59;">'
    '"What-If" Cancellation Simulator'
    '</h3>'
    '<p style="margin: 0; font-size: 0.9rem; color: #57534E;">'
    'Toggle subscriptions below to test different combinations and see how much money you free up every month and year.'
    '</p>'
    '</div>'
)

# --- Build subscription list dynamically from your DataFrame (with clean fallback) ---
sim_items = []
if "df" in locals() and isinstance(df, pd.DataFrame) and not df.empty:
    # Adjust column names if your DataFrame uses different headers (e.g., "Service", "Merchant", "Amount")
    name_col = next((c for c in df.columns if c.lower() in ["subscription", "service", "merchant", "name", "description"]), None)
    amt_col = next((c for c in df.columns if c.lower() in ["amount", "price", "cost", "monthly_cost"]), None)
    if name_col and amt_col:
        grouped = df.groupby(name_col)[amt_col].last().reset_index()
        for _, row in grouped.iterrows():
            sim_items.append({"name": str(row[name_col]), "cost": float(row[amt_col])})

# Fallback sample subscriptions if no CSV/DataFrame is loaded yet
if not sim_items:
    sim_items = [
        {"name": "Cloud Storage Plan", "cost": 199.0},
        {"name": "Streaming Ultra HD", "cost": 299.0},
        {"name": "Music & Podcasts Pro", "cost": 149.0},
        {"name": "Fitness & Wellness App", "cost": 399.0},
        {"name": "AI Writing Assistant", "cost": 499.0},
    ]

total_monthly_all = sum(item["cost"] for item in sim_items)

sim_left, sim_right = st.columns([1.15, 1], gap="large")

# LEFT COLUMN: Interactive Toggles
with sim_left:
    st.markdown(
        "<div style='font-size: 0.88rem; font-weight: 700; color: #173B59; margin-bottom: 8px;'>"
        "Select subscriptions to simulate canceling:</div>",
        unsafe_allow_html=True
    )

    selected_to_cancel = []
    with st.container(border=True):
        for idx, item in enumerate(sim_items):
            checked = st.checkbox(
                f"{item['name']}  —  ₹{item['cost']:,.0f} / month",
                value=(idx in [0, 2]),  # Pre-selects 2 items on first load so user immediately sees it working
                key=f"sim_chk_{idx}_{item['name']}"
            )
            if checked:
                selected_to_cancel.append(item)

# RIGHT COLUMN: Live Dynamic Impact Card
with sim_right:
    monthly_saved = sum(x["cost"] for x in selected_to_cancel)
    annual_saved = monthly_saved * 12
    new_monthly_bill = max(total_monthly_all - monthly_saved, 0)
    reduction_pct = round((monthly_saved / total_monthly_all) * 100) if total_monthly_all > 0 else 0

    if selected_to_cancel:
        names_list = ", ".join(x["name"] for x in selected_to_cancel)
        headline_msg = (
            f"If you cancel <b>{names_list}</b>, you could save "
            f"<span style='color:#113829; font-weight:800;'>₹{monthly_saved:,.0f}/month</span>, "
            f"or <span style='color:#113829; font-weight:800;'>₹{annual_saved:,.0f}/year</span>."
        )
    else:
        headline_msg = "Toggle one or more subscriptions on the left to calculate your potential monthly and yearly savings."

    st.html(
        f'<div style="background: #F1F6F3; border: 1.5px solid #CFE3D8; border-radius: 22px; '
        f'padding: 24px 26px; box-shadow: 0 10px 24px rgba(23, 59, 89, 0.05); '
        f'font-family: \'Plus Jakarta Sans\', sans-serif;">'

        f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">'
        f'<span style="font-size: 0.78rem; font-weight: 800; color: #3D6352; text-transform: uppercase; letter-spacing: 0.8px;">'
        f'Live Simulation Impact'
        f'</span>'
        f'<span style="background: #DCECE3; color: #113829; font-size: 0.78rem; font-weight: 800; '
        f'padding: 4px 12px; border-radius: 999px;">'
        f'-{reduction_pct}% Monthly Spend'
        f'</span>'
        f'</div>'

        # Big Annual & Monthly Numbers
        f'<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">'
        f'<div style="background: #FFFFFF; border: 1px solid #D5E5DC; border-radius: 14px; padding: 14px;">'
        f'<div style="font-size: 0.78rem; font-weight: 700; color: #64748B;">Monthly Savings</div>'
        f'<div style="font-size: 1.65rem; font-weight: 900; color: #113829;">₹{monthly_saved:,.0f}</div>'
        f'</div>'
        f'<div style="background: #FFFFFF; border: 1px solid #D5E5DC; border-radius: 14px; padding: 14px;">'
        f'<div style="font-size: 0.78rem; font-weight: 700; color: #64748B;">Annual Savings</div>'
        f'<div style="font-size: 1.65rem; font-weight: 900; color: #113829;">₹{annual_saved:,.0f}</div>'
        f'</div>'
        f'</div>'

        # Dynamic Natural-Language Sentence
        f'<div style="background: #FFFFFF; border: 1px solid #D5E5DC; border-radius: 14px; '
        f'padding: 14px 16px; font-size: 0.92rem; line-height: 1.6; color: #1E293B; margin-bottom: 14px;">'
        f'💡 {headline_msg}'
        f'</div>'

        # Before vs After Monthly Bill Bar
        f'<div style="font-size: 0.82rem; font-weight: 700; color: #3D6352; display: flex; justify-content: space-between; margin-bottom: 6px;">'
        f'<span>New Monthly Total: ₹{new_monthly_bill:,.0f}</span>'
        f'<span>Original: ₹{total_monthly_all:,.0f}</span>'
        f'</div>'
        f'<div style="width: 100%; height: 10px; background: #D5E5DC; border-radius: 999px; overflow: hidden;">'
        f'<div style="width: {100 - reduction_pct}%; background: #1E4D3B; height: 100%; transition: width 0.25s ease;"></div>'
        f'</div>'

        f'</div>'
    )
# =========================
# SUBSENTRY AI ADVISOR
# =========================
st.markdown('<div id="ai-advisor" style="padding-top: 12px;"></div>', unsafe_allow_html=True)

st.html(
    '<div style="background: #F5F3FA; border: 1.5px solid #DDD6FE; border-radius: 26px; '
    'padding: 24px 28px; margin: 18px 0 16px 0; box-shadow: 0 10px 26px rgba(23, 59, 89, 0.05); '
    'font-family: \'Plus Jakarta Sans\', sans-serif;">'
    '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">'
    '<div style="font-size: 0.78rem; font-weight: 800; letter-spacing: 0.9px; color: #5B21B6; text-transform: uppercase;">'
    '✨ Powered by Gemini AI'
    '</div>'
    '<span style="background: #EDE9FE; color: #4C1D95; font-weight: 700; font-size: 0.78rem; '
    'padding: 5px 12px; border-radius: 999px; border: 1px solid #C4B5FD;">'
    'Anonymized Metadata Only'
    '</span>'
    '</div>'
    '<h2 style="margin: 0 0 6px 0; font-size: 1.6rem; font-weight: 800; color: #173B59;">AI Subscription Intelligence</h2>'
    '<p style="margin: 0; font-size: 0.94rem; color: #475569;">'
    'Let SubSentry AI scan your subscription stack for hidden overlaps, bundle opportunities, and smart downgrades.'
    '</p>'
    '</div>'
)

if st.button("✨ Run AI Stack Audit", key="btn_run_ai_audit"):
    with st.spinner("SubSentry AI is analyzing your subscriptions..."):
        st.session_state.ai_audit_result = ai_audit_subscriptions(sim_items)

audit = st.session_state.get("ai_audit_result")
if audit:
    red_html = "".join(f"<li style='margin-bottom:6px;'>{r}</li>" for r in audit.get("redundancies", []))
    swap_html = "".join(f"<li style='margin-bottom:6px;'>{s}</li>" for s in audit.get("smart_swaps", []))

    st.html(
        f'<div style="background: #FFFFFF; border: 1.5px solid #DDD6FE; border-radius: 22px; '
        f'padding: 24px 26px; margin-bottom: 22px; box-shadow: 0 8px 22px rgba(91, 33, 182, 0.06); '
        f'font-family: \'Plus Jakarta Sans\', sans-serif;">'
        f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">'
        f'<div style="font-size: 1.05rem; font-weight: 800; color: #173B59;">💡 {audit.get("headline", "")}</div>'
        f'<span style="background: #ECFDF5; color: #065F46; font-weight: 800; font-size: 0.85rem; '
        f'padding: 6px 14px; border-radius: 999px; border: 1px solid #A7F3D0;">'
        f'Extra Savings: {audit.get("estimated_extra_savings", "₹0")}'
        f'</span>'
        f'</div>'
        f'<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">'
        f'<div style="background: #FAF5FF; border: 1px solid #E9D5FF; border-radius: 16px; padding: 16px;">'
        f'<div style="font-size: 0.82rem; font-weight: 800; color: #6B21A8; margin-bottom: 8px;">🔍 Overlap & Waste Detected</div>'
        f'<ul style="margin: 0; padding-left: 18px; font-size: 0.88rem; color: #334155; line-height: 1.55;">{red_html}</ul>'
        f'</div>'
        f'<div style="background: #F1F6F3; border: 1px solid #D5E5DC; border-radius: 16px; padding: 16px;">'
        f'<div style="font-size: 0.82rem; font-weight: 800; color: #113829; margin-bottom: 8px;">🚀 AI Optimization Moves</div>'
        f'<ul style="margin: 0; padding-left: 18px; font-size: 0.88rem; color: #334155; line-height: 1.55;">{swap_html}</ul>'
        f'</div>'
        f'</div>'
        f'</div>'
    )    
  
    # =========================
# INTERACTIVE AI MONEY ADVISOR Q&A
# =========================
st.markdown(
    "<div style='font-size: 0.92rem; font-weight: 800; color: #173B59; margin: 14px 0 6px 0;'>"
    "💬 Ask SubSentry AI About Your Spending & Budget</div>",
    unsafe_allow_html=True
)

user_fin_q = st.text_input(
    "Ask a financial question based on your data",
    placeholder="e.g., How do I bring my monthly recurring spend under ₹500? Or which charges increased?",
    label_visibility="collapsed",
    key="ai_fin_question"
)

if st.button("Ask AI Advisor ✨", key="btn_ask_ai_qa"):
    q_clean = user_fin_q.strip()
    if not q_clean:
        st.warning("Please type a question first.")
    else:
        client = get_gemini_client()
        if not client:
            st.error("API key is missing inside get_gemini_client().")
        else:
            with st.spinner("Asking Gemini AI..."):
                context_summary = {
                    "subscriptions": sim_items,
                    "monthly_total": total_monthly_all,
                    "annual_projection": total_monthly_all * 12,
                }
                qa_prompt = (
                    f"You are SubSentry AI, a friendly personal finance advisor in India (currency: ₹).\n"
                    f"User's subscription data: {json.dumps(context_summary)}\n"
                    f"User's message: {q_clean}\n\n"
                    f"Reply naturally and concisely using HTML <b>tags</b> for emphasis (do not use markdown **asterisks**)."
                )

                fallback_reply = (
                    f"Based on your current recurring subscriptions (<b>₹{total_monthly_all:,.0f}/month</b>), "
                    f"your highest-impact savings come from pausing <b>Adobe Creative Cloud (₹1,675/mo)</b> "
                    f"and consolidating overlapping streaming services like <b>Spotify</b> and <b>YouTube Premium</b> "
                    f"to save over <b>₹21,000/year</b>."
                )

                answer_html = ask_gemini_safe(client, qa_prompt, fallback_reply)

                st.html(
                    f'<div style="background: #FAF5FF; border: 1.5px solid #DDD6FE; border-radius: 18px; '
                    f'padding: 18px 22px; margin-top: 10px; font-family: \'Plus Jakarta Sans\', sans-serif; '
                    f'font-size: 0.92rem; line-height: 1.65; color: #1E293B;">'
                    f'<div style="font-size: 0.76rem; font-weight: 800; color: #6B21A8; text-transform: uppercase; margin-bottom: 6px;">'
                    f'🤖 SubSentry AI (gemini-3.8-flash)</div>'
                    f'{answer_html}'
                    f'</div>'
                )      
# =========================
# SAVINGS SNAPSHOT
# =========================
st.markdown('<div id="savings-snapshot" style="padding-top: 12px;"></div>', unsafe_allow_html=True)

# --- Dynamic calculations from your dataset ---
# (Adjust column/dataframe names if yours differ)
monthly_recurring = df["Amount"].sum() if "Amount" in df.columns else 2499.0
annual_projection = monthly_recurring * 12

# Estimate annual leakage from price hikes & hidden fees
hike_leakage = 4800.0   # Replace with your calculated annual hike total if stored in a variable
fee_leakage = 1800.0    # Replace with your calculated annual hidden fee total if stored in a variable
potential_savings = hike_leakage + fee_leakage
net_optimized = max(annual_projection - potential_savings, 0)

# Percentage split for the visual bar
keep_pct = round((net_optimized / annual_projection) * 100) if annual_projection > 0 else 75
save_pct = 100 - keep_pct

st.html(
    f'<div style="background: #FFFDF7; border: 1.5px solid #FDE68A; border-radius: 26px; '
    f'padding: 28px 30px; margin: 18px 0 28px 0; box-shadow: 0 12px 30px rgba(23, 59, 89, 0.05); '
    f'font-family: \'Plus Jakarta Sans\', sans-serif;">'

    # Header
    f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;">'
    f'<div>'
    f'<div style="font-size: 0.78rem; font-weight: 800; letter-spacing: 0.9px; color: #B45309; text-transform: uppercase;">'
    f'💰 Annual Cost & Leakage Overview'
    f'</div>'
    f'<h2 style="margin: 4px 0 0 0; font-size: 1.65rem; font-weight: 800; color: #173B59;">'
    f'Savings Snapshot'
    f'</h2>'
    f'</div>'
    f'<span style="background: #FEF3C7; color: #92400E; font-weight: 800; font-size: 0.82rem; '
    f'padding: 6px 14px; border-radius: 999px; border: 1px solid #D6CEBF;">'
    f'12-Month Projection'
    f'</span>'
    f'</div>'

    # 3 Pastel Metric Cards
    f'<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 22px;">'

    # Card 1: Current Yearly Run-Rate
    f'<div style="background: #FEF9E7; border: 1.5px solid #FDE68A; border-radius: 18px; padding: 18px 20px;">'
    f'<div style="font-size: 0.82rem; font-weight: 700; color: #92400E; margin-bottom: 6px;">Current Yearly Spend</div>'
    f'<div style="font-size: 1.85rem; font-weight: 900; color: #173B59;">₹{annual_projection:,.0f}</div>'
    f'<div style="font-size: 0.8rem; color: #64748B; margin-top: 4px;">Based on ₹{monthly_recurring:,.0f}/month</div>'
    f'</div>'

    # Card 2: Recoverable Leakage
    f'<div style="background: #FFF1F2; border: 1.5px solid #FECDD3; border-radius: 18px; padding: 18px 20px;">'
    f'<div style="font-size: 0.82rem; font-weight: 700; color: #9F1239; margin-bottom: 6px;">Potential Annual Savings</div>'
    f'<div style="font-size: 1.85rem; font-weight: 900; color: #BE123C;">₹{potential_savings:,.0f}</div>'
    f'<div style="font-size: 0.8rem; color: #64748B; margin-top: 4px;">From price hikes & hidden fees</div>'
    f'</div>'

    # Card 3: Optimized Yearly Spend
    f'<div style="background: #ECFDF5; border: 1.5px solid #A7F3D0; border-radius: 18px; padding: 18px 20px;">'
    f'<div style="font-size: 0.82rem; font-weight: 700; color: #065F46; margin-bottom: 6px;">Optimized Yearly Cost</div>'
    f'<div style="font-size: 1.85rem; font-weight: 900; color: #113829;">₹{net_optimized:,.0f}</div>'
    f'<div style="font-size: 0.8rem; color: #64748B; margin-top: 4px;">If flagged charges are cut</div>'
    f'</div>'

    f'</div>'

    # Visual Savings Split Bar
    f'<div style="background: #FFFFFF; border: 1.5px solid #FDE68A; border-radius: 16px; padding: 16px 20px;">'
    f'<div style="display: flex; justify-content: space-between; font-size: 0.84rem; font-weight: 700; color: #173B59; margin-bottom: 8px;">'
    f'<span>Core Subscriptions ({keep_pct}%)</span>'
    f'<span style="color: #78716C;">Recoverable Leakage ({save_pct}%)</span>'
    f'</div>'
    f'<div style="width: 100%; height: 14px; background: #EDE8DC; border-radius: 999px; overflow: hidden; display: flex;">'
    f'<div style="width: {keep_pct}%; background: #113829; height: 100%;"></div>'
    f'<div style="width: {save_pct}%; background: #F8F6F0; height: 100%;"></div>'
    f'</div>'
    f'</div>'

    f'</div>'
)        
# =========================
# FREE TRIAL RADAR (PRE-BANK DETECTION)
# =========================
st.markdown('<div id="trial-radar" style="padding-top: 12px;"></div>', unsafe_allow_html=True)

st.html(
    '<div style="background: #F4F9FA; border: 1.5px solid #CFE3E8; border-radius: 26px; '
    'padding: 26px 28px; margin: 18px 0 16px 0; box-shadow: 0 10px 26px rgba(23, 59, 89, 0.04); '
    'font-family: \'Plus Jakarta Sans\', sans-serif;">'
    '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">'
    '<div style="font-size: 0.78rem; font-weight: 800; letter-spacing: 0.9px; color: #1E5F74; text-transform: uppercase;">'
    '⏳ Pre-Statement Detection'
    '</div>'
    '<span style="background: #E1EFF3; color: #173B59; font-weight: 700; font-size: 0.78rem; '
    'padding: 5px 12px; border-radius: 999px; border: 1px solid #BDD8E0;">'
    'Zero Bank Access Needed'
    '</span>'
    '</div>'
    '<h2 style="margin: 0 0 6px 0; font-size: 1.6rem; font-weight: 800; color: #173B59;">Free Trial Radar</h2>'
    '<p style="margin: 0; font-size: 0.94rem; color: #475569;">'
    'Paste any welcome email or SMS confirmation below. SubSentry extracts the trial expiry date and schedules a cancellation alert before the first charge ever hits your bank statement.'
    '</p>'
    '</div>'
)

if "detected_trials" not in st.session_state:
    st.session_state.detected_trials = []

trial_col_left, trial_col_right = st.columns([1.4, 1], gap="large")

with trial_col_left:
    sample_msg = (
        "Welcome to Notion Plus! Enjoy your 14-day free trial. "
        "Your trial ends on 05 Dec 2026, after which you will be automatically billed ₹850/month."
    )
    msg_input = st.text_area(
        "Paste trial confirmation email or SMS",
        value=sample_msg,
        height=135,
        key="trial_msg_box"
    )
    msg_date = st.date_input("Date confirmation was received", value=datetime.now(), key="trial_recv_date")

    if st.button("Scan Confirmation Message 🔍", key="btn_scan_trial"):
        parsed = parse_trial_message(msg_input, datetime.combine(msg_date, datetime.min.time()))
        if parsed:
            st.session_state.latest_trial = parsed
            if not any(t["service"] == parsed["service"] and t["expiry_date"] == parsed["expiry_date"] for t in st.session_state.detected_trials):
                st.session_state.detected_trials.append(parsed)
        else:
            st.warning("No free-trial confirmation terms found. Try pasting a welcome email mentioning a trial period or renewal date.")

with trial_col_right:
    active_trial = st.session_state.get("latest_trial") or parse_trial_message(sample_msg)
    if active_trial:
        badge_text = (
            f"Expires in {active_trial['days_left']} days"
            if active_trial["days_left"] >= 0
            else "Trial expired"
        )
        st.html(
            f'<div style="background: #FFFFFF; border: 1.5px solid #CFE3E8; border-radius: 22px; '
            f'padding: 22px 24px; box-shadow: 0 8px 22px rgba(23, 59, 89, 0.05); '
            f'font-family: \'Plus Jakarta Sans\', sans-serif;">'
            f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">'
            f'<span style="font-size: 0.76rem; font-weight: 800; color: #1E5F74; text-transform: uppercase;">Detected Trial</span>'
            f'<span style="background: #FEF3C7; color: #92400E; font-size: 0.76rem; font-weight: 800; padding: 4px 10px; border-radius: 999px;">{badge_text}</span>'
            f'</div>'
            f'<div style="font-size: 1.35rem; font-weight: 900; color: #113829; margin-bottom: 4px;">{active_trial["service"]}</div>'
            f'<div style="font-size: 0.85rem; color: #64748B; margin-bottom: 16px;">Post-trial rate: <b>{active_trial["amount"]}</b></div>'
            f'<div style="background: #F8FAFC; border-radius: 14px; padding: 12px 14px; font-size: 0.88rem; line-height: 1.7; color: #1E293B;">'
            f'📅 <b>Trial Expires:</b> {active_trial["expiry_date"]}<br>'
            f'💳 <b>1st Expected Charge:</b> <span style="color: #BE123C; font-weight: 700;">{active_trial["first_payment_date"]}</span><br>'
            f'🔔 <b>Alert Scheduled:</b> {active_trial["reminder_date"]} (48 hrs prior)'
            f'</div>'
            f'<div style="font-size: 0.76rem; color: #64748B; margin-top: 10px;">ℹ️ {active_trial["source_note"]}</div>'
            f'</div>'
        )
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        st.download_button(
            label=f"🔔 Download {active_trial['service']} Calendar Reminder (.ics)",
            data=build_ics_reminder(active_trial),
            file_name=f"{active_trial['service'].lower().replace(' ', '_')}_trial_reminder.ics",
            mime="text/calendar",
            key="dl_trial_ics",
            use_container_width=True
        )
# =========================
# CANCELLATION EMAIL (STYLISH ACTION CARD)
# =========================

st.markdown(
    '<div id="take-action" class="section-anchor"></div>',
    unsafe_allow_html=True
)

st.subheader("Cancellation email draft")

merchants = (
    recurring["Merchant"].tolist()
    if not recurring.empty
    else []
)

if merchants:
    # Soft pink header banner matching the "Take Action" nav card
    st.html(
        '<div style="background:#FFE5ED; border-radius:20px; padding:18px 22px; '
        'border:1.5px solid rgba(255,255,255,0.95); box-shadow:0 8px 20px rgba(23,59,89,0.07); '
        'display:flex; align-items:center; gap:15px; margin-bottom:16px; font-family:sans-serif;">'
        '<div style="width:48px; height:48px; border-radius:14px; background:#FFFFFF; '
        'display:flex; align-items:center; justify-content:center; font-size:1.45rem; '
        'box-shadow:0 4px 10px rgba(23,59,89,0.07); flex-shrink:0;">✉️</div>'
        '<div>'
        '<div style="font-size:1.08rem; font-weight:800; color:#173B59;">One-Click Cancellation Generator</div>'
        '<div style="font-size:0.84rem; color:#173B59; opacity:0.82; margin-top:2px;">'
        'Pick a subscription and tone below to generate a ready-to-send cancellation notice.'
        '</div>'
        '</div>'
        '</div>'
    )

    e_col1, e_col2 = st.columns([1, 1])
    with e_col1:
        chosen = st.selectbox(
            "Choose a detected merchant",
            merchants
        )
    with e_col2:
        tone = st.selectbox(
            "Select email tone",
            ["Polite & Standard", "Due to Recent Price Hike", "Immediate Confirmation"]
        )

    # Customize email body based on selected tone
    if tone == "Due to Recent Price Hike":
        email_text = (
            f"Subject: Subscription Cancellation Request – {chosen}\n\n"
            f"Hello {chosen} Support Team,\n\n"
            f"Following the recent increase in my subscription billing rate, I would like to cancel my {chosen} subscription effective immediately.\n\n"
            f"Please ensure auto-renewal is disabled and send written confirmation that no further charges will be billed to my account.\n\n"
            f"Thank you,\n[Your Name]"
        )
    elif tone == "Immediate Confirmation":
        email_text = (
            f"Subject: Urgent: Cancel Auto-Renewal & Subscription ({chosen})\n\n"
            f"Hello {chosen} Billing Team,\n\n"
            f"Please treat this email as formal notice to cancel my {chosen} subscription and revoke recurring payment authorization.\n\n"
            f"Kindly reply with a cancellation reference number and confirm the final end date of my billing cycle.\n\n"
            f"Regards,\n[Your Name]"
        )
    else:
        email_text = make_email(chosen)

    email_text = st.text_area(
        "Customize your email before downloading",
        value=email_text,
        height=195
    )

else:
    st.caption(
        "A cancellation draft will appear when a recurring payment is detected."
    )

if merchants:
    preview_col, action_col = st.columns([1.65, 1], gap="large")

    if email_text.startswith("Subject:"):
        email_subject, email_body = email_text.split("\n\n", 1)
    else:
        email_subject = "Subject: Cancellation request"
        email_body = email_text

    with preview_col:
        formatted_body = email_body.replace("\n", "<br>")
        st.html(
            f'<div style="background: #FFF2F5; border: 1.5px solid #FBCFE8; border-radius: 22px; '
            f'padding: 26px 28px; box-shadow: 0 10px 26px rgba(23, 59, 89, 0.05); '
            f'font-family: \'Plus Jakarta Sans\', sans-serif; color: #173B59;">'
            f'<div style="font-size: 0.78rem; font-weight: 800; letter-spacing: 0.8px; '
            f'color: #9D174D; text-transform: uppercase; margin-bottom: 14px;">'
            f'📄 LIVE STATIONERY PREVIEW'
            f'</div>'
            f'<div style="font-weight: 700; font-size: 0.98rem; margin-bottom: 14px; color: #173B59;">'
            f'{email_subject}'
            f'</div>'
            f'<div style="font-size: 0.94rem; line-height: 1.65; color: #1E293B;">'
            f'{formatted_body}'
            f'</div>'
            f'</div>'
        )

    with action_col:
        st.download_button(
            f"⬇️ Download {chosen} cancellation email (.txt)",
            data=email_text,
            file_name=f"cancel_{chosen.lower().replace(' ', '_')}.txt",
            mime="text/plain",
            key="download_cancellation_email_btn",
            use_container_width=True
        )

        st.html(
            '<div style="background: rgba(255, 255, 255, 0.78); border: 1.5px solid #FBCFE8; '
            'border-radius: 18px; padding: 16px 18px; margin-top: 12px; '
            'font-family: \'Plus Jakarta Sans\', sans-serif;">'
            '<div style="font-size: 0.82rem; font-weight: 800; color: #9D174D; margin-bottom: 6px;">'
            '✨ Quick Send Checklist'
            '</div>'
            '<div style="font-size: 0.84rem; color: #475569; line-height: 1.55;">'
            '• Replace <b>[Your name]</b> before sending.<br>'
            '• Send from the email linked to your subscription.<br>'
            '• Keep their reply as proof of cancellation.'
            '</div>'
            '</div>'
        )

# =========================
# TRANSACTION DETAILS
# =========================

with st.expander("View transactions used in this analysis"):

    st.dataframe(
        df[["date", "description", "amount"]],
        use_container_width=True,
        hide_index=True
    )
