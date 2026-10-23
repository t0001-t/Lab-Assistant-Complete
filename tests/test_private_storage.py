"""Private visitors must never share calendar or linked notebook data."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.runtime.scriptrunner_utils.exceptions import StopException

import lab_private_storage as storage
from lab_calendar import CalendarStore


class PrivateStorageTests(unittest.TestCase):
    def test_calendar_crud_and_reopen_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = CalendarStore(storage.visitor_folder(base, "a" * 64))
            b = CalendarStore(storage.visitor_folder(base, "b" * 64))
            event = a.add_event("Private A", "2026-10-23")
            self.assertEqual(b.list_events(), [])
            b.delete_event(event)
            self.assertEqual(a.list_events()[0]["title"], "Private A")
            reopened = CalendarStore(storage.visitor_folder(base, "a" * 64))
            self.assertEqual(reopened.list_events()[0]["id"], event)
            self.assertNotIn("a" * 64, str(a.folder))

    def test_invalid_credentials_cannot_select_a_path(self):
        for token in (None, "", "../shared", "a" * 63, "g" * 64, {"token": "a" * 64}):
            with self.assertRaises(ValueError):
                storage.visitor_folder(Path("/tmp/test"), token)

    def test_no_identity_stops_before_opening_shared_storage(self):
        with patch.dict(os.environ, {"LAB_ASSISTANT_STORAGE_MODE": "private"}), \
                patch.object(storage.st, "session_state", {}), \
                patch.object(storage, "_identity", return_value=None), \
                patch.object(storage.st, "info"), \
                patch.object(storage.st, "stop", side_effect=StopException), self.assertRaises(StopException):
            storage.data_folder()

    def test_dashboard_and_notebook_use_same_private_namespace(self):
        from lab_dashboard import calendar_store, eln_store
        from lab_pages import _store
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"LAB_ASSISTANT_DATA_DIR": tmp,
                                        "LAB_ASSISTANT_STORAGE_MODE": "private"}), \
                patch.object(storage.st, "session_state", {"_lab_browser_credential": "a" * 64}):
            expected = storage.visitor_folder(Path(tmp), "a" * 64).resolve()
            self.assertEqual(calendar_store().folder, expected)
            self.assertEqual(eln_store().db.parent, expected)
            self.assertEqual(_store().db.parent, expected)
