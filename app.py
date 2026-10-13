from email.message import EmailMessage
import smtplib
from google import genai
from google.genai import types
from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, SUMMARY_REQUEST_PROMPT
import streamlit as st

# Secrets
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", 465))
SMTP_USERNAME = st.secrets["SMTP_USERNAME"]  # e.g., your-email@gmail.com
SMTP_PASSWORD = st.secrets[
    "SMTP_PASSWORD"
]  # e.g., 16-character App Password for Gmail
SENDER_NAME = st.secrets.get("Srujana", "MacroSnap Daily")


@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)


gemini_client = get_gemini_client()
MODEL_NAME = "gemini-3.8-flash"


def send_email(to_email: str, user_name: str, summary: str):
    """Sends a cleanly formatted HTML + plain text email."""
    try:
        msg = EmailMessage()
        msg["Subject"] = f"🥗 Your MacroSnap Daily Summary, {user_name}!"
        msg["From"] = f"{SENDER_NAME} <{SMTP_USERNAME}>"
        msg["To"] = to_email

        # Plain text fallback
        plain_body = (
            f"Hi {user_name},\n\nHere is your nutrition summary:\n\n{summary}"
        )
        msg.set_content(plain_body)

        # HTML formatting for clean readability
        formatted_summary = summary.replace("\n", "<br>")
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #222; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #f7fafc; padding: 20px; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <h2 style="color: #2b6cb0; margin-top: 0;">🥗 MacroSnap Daily Summary</h2>
                    <p>Hi <strong>{user_name}</strong>,</p>
                    <p>Here is the breakdown of your logged meals:</p>
                    <div style="background-color: #ffffff; padding: 15px; border-radius: 6px; border-left: 4px solid #3182ce; margin: 15px 0;">
                        {formatted_summary}
                    </div>
                    <p style="color: #718096; font-size: 0.85em; margin-bottom: 0;">Keep hitting your targets!</p>
                </div>
            </body>
        </html>
        """
        msg.add_alternative(html_body, subtype="html")

        # Send via SSL (Port 465) or STARTTLS (Port 587)
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)

        return True, "Email sent successfully"
    except Exception as error:
        return False, str(error)


def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):
    st.session_state.message.append(
        {"role": role, "kind": kind, "content": content}
    )
    render_message(st.session_state.message[-1])


def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as error:
        return f"Sorry, there was an error: {error}"


# Step 1: Onboarding (Name and Email)
if "onboarded" not in st.session_state:
    st.title("MacroSnap 🥗")
    st.caption("Snap it. Track it. Get your nutrition breakdown via email.")

    with st.form("onboarding_form"):
        name = st.text_input("Your Name")
        email = st.text_input(
            "Email Address",
            placeholder="you@example.com",
            help="Your daily nutrition summaries will be delivered here",
        )
        submitted = st.form_submit_button("Let's go")

    if submitted:
        if not name.strip() or not email.strip() or "@" not in email:
            st.warning("Please provide a valid name and email address.")
        else:
            st.session_state.name = name.strip()
            st.session_state.email = email.strip()

            # Initialize chat
            st.session_state.chat = gemini_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT
                ),
            )
            st.session_state.message = []
            st.session_state.onboarded = True
            st.rerun()
    st.stop()

# Step 2: Main Interface
header_col, button_col = st.columns([5, 2], vertical_alignment="center")

with header_col:
    st.title("MacroSnap 🥗")

with button_col:
    send_disabled = len(st.session_state.message) <= 1

    if st.button("📧 Email Summary", disabled=send_disabled, use_container_width=True):
        with st.spinner("Generating your daily summary..."):
            summary = ask_gemini([SUMMARY_REQUEST_PROMPT])
            success, info = send_email(
                st.session_state.email, st.session_state.name, summary
            )

            if success:
                st.success(f"Summary sent to {st.session_state.email} 📩")
            else:
                st.error(f"Couldn't send email: {info}")

st.caption(
    f"Logged in as **{st.session_state.name}** · Reports send to: **{st.session_state.email}**"
)

# Render Chat History
if not st.session_state.message:
    add_message(
        "assistant",
        "text",
        WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.name),
    )
else:
    for message in st.session_state.message:
        render_message(message)

# Chat Input (Text or Image)
user_input = st.chat_input(
    "Ask a question or upload a meal photo...",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(
            types.Part.from_bytes(data=photo_bytes, mime_type=photo.type)
        )

    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append(
            "Analyze this meal. Identify the items and estimate the calories, protein, carbs, and fats."
        )

    with st.spinner("Analyzing your meal..."):
        answer = ask_gemini(parts)

    add_message("assistant", "text", answer)