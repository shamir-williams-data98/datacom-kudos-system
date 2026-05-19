# DEBUG_LOG.md — `process_data.py` Bug Investigation

**Script:** `Datacom/process_data.py`
**Date:** 2024-01-15 (error log) → 2026-05-18 (investigation)
**Status:** ✅ Fixed and verified

---

## Phase 1 — Initial Code Review

### Prompt
> This is a legacy Python script (Datacome/process_data.py). Please provide a high-level summary of what it's supposed to do. Then, break down your explanation function by function.

### Key Findings

The script is a **customer analytics ETL pipeline** built around a `DataProcessor` class:

| Function | Purpose | Side Effects |
|---|---|---|
| `load_data()` | Reads `customers.csv` into `self.customers` dict | Mutates `self.customers` |
| `process_transactions()` | Reads `transactions.csv`, updates customer totals | Mutates `self.customers` + `self.transactions` |
| `calculate_customer_metrics()` | Computes summary analytics | Pure computation (no mutations) |
| `find_matches()` | Substring search on customer fields | None — **dead code, never called** |
| `generate_report()` | Writes JSON reports to disk | File I/O |
| `export_customer_data()` | Exports customers as CSV or JSON | File I/O |

### My Notes
> The initial review flagged 9 potential issues. The two most important were:
> 1. `top_customers` on line 114 returns **tuples** `(customer_id, data_dict)` instead of flat dicts
> 2. `self.reports` is initialized but **never used** — dead state
> 3. `export_customer_data` parameter `format` **shadows the Python built-in**
>
> At this point I suspected the tuple issue was the root cause of downstream failures, but I needed the error log to confirm.

---

## Phase 2 — Error Log Analysis

### Prompt
> Given the following function and the associated error log, what is the most likely root cause of the failure?

### The Error Log
```
2024-01-15 02:30:16,123 - INFO - Exported customer data to customers_export.csv
2024-01-15 02:30:16,234 - ERROR - Error exporting data: 'dict' object has no attribute 'keys'
2024-01-15 02:30:16,235 - ERROR - Data processing completed successfully
```

### Root Cause Trace (Step-by-Step)

**Step 1 — Where does the error occur?**
The CSV export succeeded (line 224 in `main()`), so the failure is on the **JSON export** — line 225: `export_customer_data("customers_export.json", "json")`.

**Step 2 — Where is `.keys()` called?**
Line 180 in `export_customer_data`:
```python
fieldnames = ["customer_id"] + list(
    next(iter(self.customers.values())).keys()   # ← .keys() called here
)
```

**Step 3 — How does state get corrupted?**
`calculate_customer_metrics()` at lines 112–114 stores **direct references** (not copies) of `self.customers` data inside the metrics dict:
```python
customer_list = [(cid, data) for cid, data in self.customers.items()]
# data is a REFERENCE to the same object in self.customers, not a copy
```

**Step 4 — The crash**
When `json.dump()` encounters a value that isn't a plain dict (e.g., a tuple from `top_customers`, or corrupted data from shared references), it raises `AttributeError: 'dict' object has no attribute 'keys'`.

### My Notes
> The key insight was the **shared reference problem**. The `data` variable in the list comprehension on line 112 points to the exact same dict object living inside `self.customers`. Any mutation through one reference silently affects the other.
>
> Also notable: the broad `except Exception` on line 198 swallows the real traceback, which is why the production error message is so vague.

---

## Phase 3 — Writing the Failing Tests

### Prompt
> Write a Python unit test using the 'unittest' library that is specifically designed to fail in the same way the error log shows.

### Tests Created → `TEST_CASES.py`

| Test # | Name | What It Proves |
|---|---|---|
| 1 | `test_top_customers_are_dicts` | `top_customers[0]` is a tuple, not a dict |
| 2 | `test_top_customers_have_customer_id_key` | Tuples don't support `entry["customer_id"]` |
| 3 | `test_top_customers_json_roundtrip_structure` | JSON serialises tuples as arrays — report on disk is structurally wrong |
| 4 | `test_csv_export_fails_on_non_dict_customer_value` | Injecting a non-dict value crashes export via `.keys()` |
| 5 | `test_full_pipeline_export_succeeds_after_metrics` | Full `main()` call sequence must not corrupt state |

### Design Decision
> Tests 1–3 use **no file I/O** — they inject state directly into the `DataProcessor` object and test in-memory. This makes them fast and deterministic.
>
> Tests 4–5 use `tempfile.TemporaryDirectory()` for file I/O so they clean up after themselves.

---

## Phase 4 — Running Tests (Before Fix)

### Command
```bash
python3 -m pytest TEST_CASES.py -v
```

### Result: 4 FAILED, 1 PASSED ✅ (as designed)
```
FAILED  test_top_customers_are_dicts
        → ('C003', {'name': 'Carol White', ...}) is not an instance of <class 'dict'>

FAILED  test_top_customers_have_customer_id_key
        → 'customer_id' not found in ('C003', {...})

FAILED  test_top_customers_json_roundtrip_structure
        → ['C003', {...}] is not an instance of <class 'dict'>

FAILED  test_csv_export_fails_on_non_dict_customer_value
        → False is not true (export crashed and returned False)

PASSED  test_full_pipeline_export_succeeds_after_metrics
        → JSON export works when all customer values are valid dicts
```

### My Notes
> Test 5 passing was informative — it proved the JSON export itself isn't broken. The crash only happens when **corrupted (non-dict) data** enters `self.customers`. This narrowed the fix: we don't need to rewrite the export — we just need to validate inputs and fix the tuple structure.

---

## Phase 5 — Applying the Fix

### Changes Made to `process_data.py`

#### Fix 1: `calculate_customer_metrics()` — Return dicts, not tuples (lines 111–124)

```diff
-        # Find top customers by total spent
-        customer_list = [(cid, data) for cid, data in self.customers.items()]
-        customer_list.sort(key=lambda x: x[1]["total_spent"], reverse=True)
+        # Find top customers by total spent — return independent dicts, not tuples
+        customer_list = sorted(
+            (
+                {"customer_id": cid, **dict(data)}
+                for cid, data in self.customers.items()
+            ),
+            key=lambda x: x["total_spent"],
+            reverse=True,
+        )
         metrics["top_customers"] = customer_list[:10]
```

**Why `dict(data)`?** Creates a shallow copy so `top_customers` entries are independent from `self.customers`. No shared reference problem.

#### Fix 2: Category breakdown — `Counter` instead of manual loop (lines 122–124)

```diff
-        # Calculate category breakdown
-        for transaction in self.transactions:
-            category = transaction["category"]
-            if category not in metrics["category_breakdown"]:
-                metrics["category_breakdown"][category] = 0
-            metrics["category_breakdown"][category] += 1
+        # Calculate category breakdown using Counter for O(n) single-pass
+        metrics["category_breakdown"] = dict(
+            Counter(t["category"] for t in self.transactions)
+        )
```

**Why?** `Counter` is implemented in C under the hood and avoids repeated Python-level dict lookups. Also more readable.

#### Fix 3: `export_customer_data()` — Validate before using `.keys()` (lines 181–190)

```diff
+            # Filter to only valid dict records; warn about any bad entries
+            valid_customers = {}
+            for cid, data in self.customers.items():
+                if isinstance(data, dict):
+                    valid_customers[cid] = data
+                else:
+                    logger.warning(
+                        f"Skipping customer {cid}: expected dict, "
+                        f"got {type(data).__name__}"
+                    )
```

**Why?** Instead of crashing the entire export, we skip bad records and log a clear warning. The export still succeeds for all valid customers.

#### Fix 4: Better error logging (line 207)

```diff
-            logger.error(f"Error exporting data: {e}")
+            logger.error(f"Error exporting data: {e}", exc_info=True)
```

**Why?** `exc_info=True` prints the full traceback. Without it, we only get the vague message we saw in the error log.

---

## Phase 6 — Running Tests (After Fix)

### Command
```bash
python3 -m pytest TEST_CASES.py -v
```

### Result: 5 PASSED ✅
```
TEST_CASES.py::TestTopCustomersBug::test_top_customers_are_dicts           PASSED [ 20%]
TEST_CASES.py::TestTopCustomersBug::test_top_customers_have_customer_id_key PASSED [ 40%]
TEST_CASES.py::TestTopCustomersBug::test_top_customers_json_roundtrip_structure PASSED [ 60%]
TEST_CASES.py::TestExportKeysBug::test_csv_export_fails_on_non_dict_customer_value PASSED [ 80%]
TEST_CASES.py::TestExportKeysBug::test_full_pipeline_export_succeeds_after_metrics PASSED [100%]

============================== 5 passed in 0.01s ===============================
```

---

## Summary of Remaining Issues (Not Fixed)

These were identified in Phase 1 but **not in scope** for this fix:

| # | Issue | Severity |
|---|---|---|
| 1 | `self.reports` is initialized but never used (dead state) | Low |
| 2 | `find_matches()` is dead code — never called | Low |
| 3 | `format` parameter shadows Python built-in | Low |
| 4 | No CLI argument support — all paths hardcoded in `main()` | Medium |
| 5 | Date fields stored as raw strings — no parsing or validation | Medium |
| 6 | Orphan transactions (unknown `customer_id`) still appended to `self.transactions` | Medium |
