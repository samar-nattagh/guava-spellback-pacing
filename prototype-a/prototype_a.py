"""
Prototype A: meeting booking with an explicit name spell-back (original speed).

Based on my original test agent. The name, email and booking code is unchanged from the
version I tested on a live call; I added an opening question and removed the company step.

Flow:
    "How can I help?"
        not a booking -> explain this line only books meetings, hang up
        booking       -> name  -> spell back -> "Is that right?"  (no -> caller spells it)
                      -> email -> check it's valid -> spell back -> "Is that right?"  (no -> caller spells it)
                      -> pick a time -> confirm the booking, hang up
    Each detail gets 3 tries before the agent apologizes and hands off.

Run:  .venv/bin/python agent.py
"""

import logging
import os
import re
from datetime import date, datetime, timedelta

import guava
from guava import logging_utils

logger = logging.getLogger("prototype_a")

MAX_ATTEMPTS = 3
ACK = "Briefly acknowledge each answer with a short phrase like 'Got it' or 'Thanks' before moving on."

agent = guava.Agent(
    name="Riley",
    organization="Northwind Consulting",  # fictional
    purpose="Help callers book a 30-minute intro meeting.",
)


# --- Spoken forms and checks (plain Python) -------------------------------------------
def letters_only(text: str) -> str:
    return re.sub(r"[^A-Za-z]", "", text or "").upper()


def spell_name(name: str) -> str:
    """'Sam Lee' -> 'S, A, M. Then, L, E, E'  (commas make the voice pause per letter)."""
    # A caller-spelled name looks like 'S A M / L E E': split on '/' so the letters stay together.
    parts = (name or "").split("/") if "/" in (name or "") else (name or "").split()
    words = [letters_only(w) for w in parts]
    return ". Then, ".join(", ".join(w) for w in words if w)


SYMBOL_WORDS = {".": "dot", "_": "underscore", "-": "dash", "+": "plus"}
COMMON_DOMAINS = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "aol.com"}


def spell_email(email: str) -> str:
    """'sam.lee@acme.io' -> 's, a, m, dot, l, e, e, at, a, c, m, e, dot, i, o'"""
    local, _, domain = email.lower().partition("@")
    spoken_local = ", ".join(SYMBOL_WORDS.get(ch, ch) for ch in local)
    if domain in COMMON_DOMAINS:
        spoken_domain = domain.replace(".", " dot ")  # "gmail dot com"
    else:
        spoken_domain = ", ".join(SYMBOL_WORDS.get(ch, ch) for ch in domain)
    return f"{spoken_local}, at, {spoken_domain}"


EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


def normalize_email(raw: str) -> str:
    """Lowercase, drop spaces, and map a spoken 'at'/'dot' if the agent left them in."""
    e = (raw or "").strip().lower()
    e = re.sub(r"\s+at\s+", "@", e)
    e = re.sub(r"\s+dot\s+", ".", e)
    return e.replace(" ", "")


def meeting_slots(today: date | None = None) -> list[str]:
    """Next 3 weekdays at 10:00 and 14:00 (made up; a real version would read a calendar)."""
    day, slots = today or date.today(), []
    while len(slots) < 6:
        day += timedelta(days=1)
        if day.weekday() < 5:
            slots += [f"{day.isoformat()}T10:00", f"{day.isoformat()}T14:00"]
    return slots


def too_many_attempts(call: guava.Call, detail: str) -> bool:
    key = f"attempts_{detail}"
    attempts = call.get_variable(key, 0) + 1
    call.set_variable(key, attempts)
    if attempts >= MAX_ATTEMPTS:
        logger.warning("Giving up on %s after %d attempts.", detail, attempts)
        call.hangup("Apologize that we're having trouble getting that right, and say someone "
                    "from the team will follow up to finish scheduling.")
        return True
    return False


def ask_yes_no(call: guava.Call, task_id: str, readback: str) -> None:
    """Speak an exact read-back, then collect a yes/no."""
    call.set_task(
        task_id,
        checklist=[
            guava.Say(readback),  # spoken word for word
            guava.Field(key=f"{task_id}_ok", field_type="multiple_choice", choices=["yes", "no"],
                        question="Is that right?"),
        ],
    )


# --- 1. Why are you calling? ------------------------------------------------------------
@agent.on_call_start
def on_call_start(call: guava.Call) -> None:
    call.set_task(
        "reason",
        checklist=[guava.Field(
            key="reason", field_type="multiple_choice",
            choices=["book a meeting", "something else"],
            question="Hi, thanks for calling Northwind Consulting. How can I help you today?")],
    )


@agent.on_task_complete("reason")
def on_reason(call: guava.Call) -> None:
    if call.get_field("reason") != "book a meeting":
        call.hangup("Explain politely that this line is only for booking intro meetings, "
                    "suggest they email the team for anything else, and say goodbye.")
        return
    call.set_task(
        "name",
        objective="The caller wants to book a meeting. Get their name. " + ACK,
        checklist=[guava.Field(key="full_name", field_type="text",
                               question="Could I get your full name, first and last?")],
    )


# --- 2. Name -----------------------------------------------------------------------------
@agent.on_task_complete("name")
def on_name(call: guava.Call) -> None:
    logger.info("Heard name: %r", call.get_field("full_name"))
    call.set_variable("name", call.get_field("full_name"))
    ask_yes_no(call, "confirm_name", f"I have that as {spell_name(call.get_field('full_name'))}.")


# Known issue: if the caller corrects the spelling during this confirmation instead of
# saying "no", the agent may confirm the correction aloud, but only "yes"/"no" is saved,
# so the original misheard name is kept. See README > Next.
@agent.on_task_complete("confirm_name")
def on_confirm_name(call: guava.Call) -> None:
    logger.info("Name confirmation answer: %r", call.get_field("confirm_name_ok"))
    if call.get_field("confirm_name_ok") == "yes":
        return ask_email(call)
    if too_many_attempts(call, "name"):
        return
    call.set_task(
        "spell_name",
        objective="The caller said we have their name spelled wrong. " + ACK,
        checklist=[guava.Field(
            key="name_spelling", field_type="text",
            description=("Apologize briefly and ask them to spell their full name letter by letter. "
                         "Record only the letters, with ' / ' between first and last name, "
                         "e.g. 'S A M / L E E'. 'M as in Mary' means just 'M'."))],
    )


@agent.on_task_complete("spell_name")
def on_spell_name(call: guava.Call) -> None:
    logger.info("Heard spelling: %r", call.get_field("name_spelling"))
    call.set_variable("name", call.get_field("name_spelling"))
    ask_yes_no(call, "confirm_name", f"Thanks. So that's {spell_name(call.get_field('name_spelling'))}.")


# --- 3. Email ----------------------------------------------------------------------------
def ask_email(call: guava.Call) -> None:
    call.set_task(
        "email",
        objective=ACK,
        checklist=[guava.Field(
            key="email", field_type="text",
            description=("Ask for the best email to send the invite to. Record it in standard "
                         "written form, e.g. 'sam.lee@acme.com' (convert spoken 'at' and 'dot')."))],
    )


@agent.on_task_complete("email")
def on_email(call: guava.Call) -> None:
    logger.info("Heard email: %r", call.get_field("email"))
    check_and_read_back_email(call, call.get_field("email"))


@agent.on_task_complete("spell_email")
def on_spell_email(call: guava.Call) -> None:
    check_and_read_back_email(call, call.get_field("email_spelling"))


def check_and_read_back_email(call: guava.Call, raw: str) -> None:
    email = normalize_email(raw)
    if not EMAIL_RE.match(email):
        logger.info("Invalid email recorded: %r", raw)
        if not too_many_attempts(call, "email"):
            call.retry_task(reason="That doesn't look like a complete email address "
                                   "(it needs a name, an @, and a domain like acme.com). Ask again.")
        return
    call.set_variable("email", email)
    ask_yes_no(call, "confirm_email", f"I'll send the invite to {spell_email(email)}.")


@agent.on_task_complete("confirm_email")
def on_confirm_email(call: guava.Call) -> None:
    if call.get_field("confirm_email_ok") == "yes":
        return ask_time(call)
    if too_many_attempts(call, "email"):
        return
    call.set_task(
        "spell_email",
        objective="The caller said the email is wrong. " + ACK,
        checklist=[guava.Field(
            key="email_spelling", field_type="text",
            description=("Apologize briefly and ask them to spell the email slowly, character by "
                         "character. Record it in written form, e.g. 'sam.lee@acme.com'."))],
    )


# --- 4. Meeting time ---------------------------------------------------------------------
def ask_time(call: guava.Call) -> None:
    call.set_task(
        "pick_time",
        objective="Offer a few of the available times (Pacific time) and book one. " + ACK,
        checklist=[guava.Field(key="meeting_time", field_type="calendar_slot", choices=meeting_slots(),
                               description="A 30-minute slot that works for the caller")],
    )


@agent.on_task_complete("pick_time")
def on_time(call: guava.Call) -> None:
    when = datetime.fromisoformat(call.get_field("meeting_time"))
    spoken_when = f"{when:%A, %B} {when.day} at {when:%-I %p}"  # "Monday, November 9 at 2 PM"
    logger.info("BOOKED: %s | %s | %s", call.get_variable("name"), call.get_variable("email"),
                when.isoformat())
    call.hangup(f"Confirm briefly that the meeting is booked for {spoken_when} Pacific and the "
                "invite is on its way to their email, thank them, and say goodbye.")


# --- Off-script questions and logging ---------------------------------------------------
@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    logger.info("Question: %s", question)
    return "This is a 30-minute intro call with our team. Details will be in the email invite."


@agent.on_session_end
def on_session_end(call: guava.Call, event) -> None:
    logger.info("Session ended: reason=%s booked=%s", event.termination_reason,
                call.get_field("meeting_time"))
    # Everything the agent recorded, including steps that never finished.
    for key in ("reason", "full_name", "confirm_name_ok", "name_spelling", "email",
                "confirm_email_ok", "email_spelling", "meeting_time"):
        if call.get_field(key) is not None:
            logger.info("Recorded %s = %r", key, call.get_field(key))


if __name__ == "__main__":
    logging_utils.configure_logging()
    agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])  # your Guava phone number
