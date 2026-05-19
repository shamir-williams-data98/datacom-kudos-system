#!/usr/bin/env python3
"""
TEST_CASES.py — Regression tests for bugs identified in process_data.py
======================================================================

All three tests below are designed to FAIL against the current (buggy) code,
reproducing the same failure class observed in the error log:

    ERROR - Error exporting data: 'dict' object has no attribute 'keys'

Root cause traced to:
  - calculate_customer_metrics() lines 112–114: stores top_customers as a list
    of raw (customer_id, data_dict) TUPLES rather than dicts. The data_dict
    values are live references into self.customers, not copies.
  - export_customer_data() line 180: calls .keys() on the first customer value.
    If self.customers is ever fed a non-dict value (e.g. a list, or a row object),
    this raises AttributeError — exactly matching the log.
"""

import unittest
import json
import os
import tempfile
import sys

# Allow running from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from process_data import DataProcessor


# ---------------------------------------------------------------------------
# Shared fixture data — mirrors a realistic pipeline state after load + process
# ---------------------------------------------------------------------------
SAMPLE_CUSTOMERS = {
    "C001": {
        "name": "Alice Smith",
        "email": "alice@example.com",
        "join_date": "2023-01-15",
        "total_spent": 850.00,
        "transaction_count": 8,
    },
    "C002": {
        "name": "Bob Jones",
        "email": "bob@example.com",
        "join_date": "2023-03-10",
        "total_spent": 420.00,
        "transaction_count": 4,
    },
    "C003": {
        "name": "Carol White",
        "email": "carol@example.com",
        "join_date": "2023-06-22",
        "total_spent": 1200.00,
        "transaction_count": 12,
    },
    "C004": {
        "name": "Dan Brown",
        "email": "dan@example.com",
        "join_date": "2023-08-01",
        "total_spent": 190.00,
        "transaction_count": 2,
    },
    "C005": {
        "name": "Eva Green",
        "email": "eva@example.com",
        "join_date": "2023-09-15",
        "total_spent": 660.00,
        "transaction_count": 6,
    },
}

SAMPLE_TRANSACTIONS = [
    {"transaction_id": "T001", "customer_id": "C001", "amount": 100.00, "date": "2024-01-01", "category": "Electronics"},
    {"transaction_id": "T002", "customer_id": "C002", "amount": 50.00,  "date": "2024-01-02", "category": "Clothing"},
    {"transaction_id": "T003", "customer_id": "C003", "amount": 200.00, "date": "2024-01-03", "category": "Electronics"},
    {"transaction_id": "T004", "customer_id": "C004", "amount": 30.00,  "date": "2024-01-04", "category": "Food"},
    {"transaction_id": "T005", "customer_id": "C005", "amount": 150.00, "date": "2024-01-05", "category": "Clothing"},
]


class TestTopCustomersBug(unittest.TestCase):
    """
    Tests targeting the bug on lines 112–114 of process_data.py:

        customer_list = [(cid, data) for cid, data in self.customers.items()]
        customer_list.sort(key=lambda x: x[1]["total_spent"], reverse=True)
        metrics["top_customers"] = customer_list[:10]   # <-- returns TUPLES

    Expected behaviour : each entry in top_customers is a dict
    Actual behaviour   : each entry is a (customer_id, dict) tuple
    """

    def setUp(self):
        self.processor = DataProcessor("dummy_not_needed.csv")
        # Inject state directly — no CSV files required
        self.processor.customers = {k: dict(v) for k, v in SAMPLE_CUSTOMERS.items()}
        self.processor.transactions = [dict(t) for t in SAMPLE_TRANSACTIONS]

    # ------------------------------------------------------------------
    # TEST 1 — top_customers entries must be dicts, not tuples
    # ------------------------------------------------------------------
    def test_top_customers_are_dicts(self):
        """
        EXPECTED TO FAIL.

        The current code returns top_customers as a list of tuples:
            [(customer_id, {name, email, ...}), ...]

        A caller that treats each entry as a dict (e.g. entry["name"]) will
        raise a TypeError — the same class of error seen in the error log.
        """
        metrics = self.processor.calculate_customer_metrics()
        top = metrics["top_customers"]

        self.assertGreater(len(top), 0, "top_customers should not be empty")

        first = top[0]

        # ---- THIS ASSERTION WILL FAIL ----
        # first is actually a tuple like ('C003', {'name': 'Carol White', ...})
        self.assertIsInstance(
            first,
            dict,
            f"Each top_customers entry should be a dict, "
            f"but got {type(first).__name__}: {repr(first)}"
        )

    # ------------------------------------------------------------------
    # TEST 2 — top_customers entries must expose a 'customer_id' key
    # ------------------------------------------------------------------
    def test_top_customers_have_customer_id_key(self):
        """
        EXPECTED TO FAIL.

        If top_customers were correctly formatted dicts, accessing
        entry["customer_id"] would work. On a tuple it raises TypeError,
        matching the 'object has no attribute' family of errors in the log.
        """
        metrics = self.processor.calculate_customer_metrics()
        top = metrics["top_customers"]

        for entry in top:
            # ---- THIS WILL FAIL on the first iteration ----
            # entry is a tuple; 'customer_id' is not a valid tuple index
            self.assertIn(
                "customer_id",
                entry,
                f"Expected 'customer_id' key in entry, got: {repr(entry)}"
            )

    # ------------------------------------------------------------------
    # TEST 3 — top_customers JSON roundtrip must produce dicts, not arrays
    # ------------------------------------------------------------------
    def test_top_customers_json_roundtrip_structure(self):
        """
        EXPECTED TO FAIL.

        JSON serialises Python tuples as arrays, so after a roundtrip:
            top_customers[0]  becomes  ["C003", {"name": "Carol White", ...}]
        instead of the expected dict.

        This proves the metrics report written to disk is structurally wrong.
        """
        metrics = self.processor.calculate_customer_metrics()

        # json.dumps / loads simulates what generate_report() writes to disk
        roundtripped = json.loads(json.dumps(metrics))

        top = roundtripped["top_customers"]
        self.assertGreater(len(top), 0)

        first = top[0]

        # ---- THIS WILL FAIL ----
        # first is ["C003", {...}]  (a 2-element list), not a dict
        self.assertIsInstance(
            first,
            dict,
            f"After JSON roundtrip, top_customers[0] should be a dict "
            f"but got {type(first).__name__}: {repr(first)}"
        )


class TestExportKeysBug(unittest.TestCase):
    """
    Tests targeting the 'dict' object has no attribute 'keys' error
    that appears in the error log during export_customer_data().

    Line 180:
        next(iter(self.customers.values())).keys()

    This line assumes every value in self.customers is a plain dict.
    If ANY value is a non-dict type (a list, a tuple, a string, etc.),
    .keys() raises AttributeError — exactly matching the log.
    """

    def setUp(self):
        self.processor = DataProcessor("dummy_not_needed.csv")
        self.processor.customers = {k: dict(v) for k, v in SAMPLE_CUSTOMERS.items()}
        self.processor.transactions = [dict(t) for t in SAMPLE_TRANSACTIONS]

    # ------------------------------------------------------------------
    # TEST 4 — CSV export fails when a customer value is not a dict
    # ------------------------------------------------------------------
    def test_csv_export_fails_on_non_dict_customer_value(self):
        """
        EXPECTED TO FAIL (export returns False, not True).

        Injects a corrupted customer record (a list instead of a dict)
        to directly trigger:
            AttributeError: 'list' object has no attribute 'keys'

        This is structurally identical to the production error
        ('dict' object has no attribute 'keys') — both arise because
        line 180 blindly calls .keys() without type-checking the value.
        """
        # Inject a malformed record — simulates data corruption from an
        # upstream process (e.g. a bad CSV row or an ORM returning a list)
        self.processor.customers["C_BAD"] = ["not", "a", "dict"]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_file = os.path.join(tmpdir, "customers_export.csv")

            result = self.processor.export_customer_data(export_file, format="csv")

            # ---- THIS ASSERTION WILL FAIL ----
            # export_customer_data() catches the AttributeError internally,
            # logs it, and returns False — matching the error log exactly.
            self.assertTrue(
                result,
                "export_customer_data should return True, but returned False. "
                "Check logs for: 'list' object has no attribute 'keys' — "
                "same root cause as the production error on line 180."
            )

    # ------------------------------------------------------------------
    # TEST 5 — Full pipeline sequence from main() must complete cleanly
    # ------------------------------------------------------------------
    def test_full_pipeline_export_succeeds_after_metrics(self):
        """
        EXPECTED TO FAIL (export_customer_data returns False).

        Replicates the exact call order in main():
            1. generate_report("metrics")   → internally mutates metrics state
            2. export_customer_data(json)   → must still succeed

        The error log shows steps 1–5 (reports) succeed, then step 6
        (JSON export) fails. This test catches that regression.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_file = os.path.join(tmpdir, "metrics.json")
            export_file  = os.path.join(tmpdir, "customers_export.json")

            # Step 1 — mirrors main() line 220
            gen_ok = self.processor.generate_report("metrics", metrics_file)
            self.assertTrue(gen_ok, "Metrics report generation should succeed")

            # Step 2 — mirrors main() line 225
            export_ok = self.processor.export_customer_data(export_file, format="json")

            # ---- THIS ASSERTION WILL FAIL if export returns False ----
            self.assertTrue(
                export_ok,
                "JSON export should succeed after metrics generation, "
                "but returned False. Check logs for: "
                "'dict' object has no attribute 'keys'"
            )

            # Bonus: verify exported file is valid and complete
            with open(export_file) as f:
                exported = json.load(f)
            self.assertEqual(
                len(exported),
                len(self.processor.customers),
                "Exported JSON should contain all customers"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
