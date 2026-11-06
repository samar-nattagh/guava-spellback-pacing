"""Offline tests for Prototype B:  .venv/bin/python -m unittest test_prototype_b -v"""

import unittest

from guava.commands import RetryTaskCommand, SetPersona, SetTaskCommand
from guava.testing import MockCall

import prototype_b as a


def mock(**fields) -> MockCall:
    call = MockCall()
    for k, v in fields.items():
        call.set_field(k, v)
    return call


def tasks(call: MockCall) -> list[str]:
    return [c.task_id for c in call._command_queue if isinstance(c, SetTaskCommand)]


def spoken(call: MockCall) -> str:
    """The verbatim line in the last task sent."""
    task = [c for c in call._command_queue if isinstance(c, SetTaskCommand)][-1]
    return task.model_dump()["action_items"][0]["statement"]


class Flow(unittest.TestCase):
    def test_booking_goes_to_name(self):
        call = mock(reason="book a meeting")
        a.on_reason(call)
        self.assertEqual(tasks(call), ["name"])

    def test_other_reason_hangs_up(self):
        call = mock(reason="something else")
        a.on_reason(call)
        self.assertEqual(tasks(call), [])

    def test_name_is_spelled_back(self):
        call = mock(full_name="Jordan Rivera")
        a.on_name(call)
        self.assertEqual(spoken(call), "I have that as J, O, R, D, A, N. Then, R, I, V, E, R, A.")

    def test_name_no_asks_for_spelling(self):
        call = mock(confirm_name_ok="no")
        a.on_confirm_name(call)
        self.assertEqual(tasks(call), ["spell_name"])

    def test_name_yes_asks_for_email(self):
        call = mock(confirm_name_ok="yes")
        a.on_confirm_name(call)
        self.assertEqual(tasks(call), ["email"])

    def test_bad_email_is_retried(self):
        call = mock(email="jordan at gmail")
        a.on_email(call)
        self.assertTrue([c for c in call._command_queue if isinstance(c, RetryTaskCommand)])

    def test_good_email_is_spelled_back(self):
        call = mock(email="jordan@gmail.com")
        a.on_email(call)
        self.assertEqual(spoken(call), "I'll send the invite to j, o, r, d, a, n, at, gmail dot com.")

    def test_email_yes_asks_for_time(self):
        call = mock(confirm_email_ok="yes")
        a.on_confirm_email(call)
        self.assertEqual(tasks(call), ["pick_time"])

    def test_gives_up_after_three_tries(self):
        call = mock(confirm_name_ok="no")
        for _ in range(a.MAX_ATTEMPTS):
            a.on_confirm_name(call)
        self.assertEqual(tasks(call), ["spell_name"] * (a.MAX_ATTEMPTS - 1))


    # --- Prototype B: the only behavior change -----------------------------------------
    def speeds(self, call):
        return [c.tts_speed for c in call._command_queue if isinstance(c, SetPersona)]

    def test_name_spell_back_is_slow(self):
        call = mock(full_name="Jordan Rivera")
        a.on_name(call)
        self.assertEqual(self.speeds(call), ["x-slow"])

    def test_spelled_name_read_back_is_slow(self):
        call = mock(name_spelling="J O R D A N / R I V E R A")
        a.on_spell_name(call)
        self.assertEqual(self.speeds(call), ["x-slow"])

    def test_speed_returns_to_normal_after_answer(self):
        for answer in ("yes", "no"):
            call = mock(confirm_name_ok=answer)
            a.on_confirm_name(call)
            self.assertEqual(self.speeds(call), ["medium"])

    def test_email_read_back_is_not_slowed(self):
        call = mock(email="jordan@gmail.com")
        a.on_email(call)
        self.assertEqual(self.speeds(call), [])


if __name__ == "__main__":
    unittest.main()
