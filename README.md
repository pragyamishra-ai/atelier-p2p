# Atelier P2P

AI for procure-to-pay in luxury retail, from invoice PDFs to validated data, quality checks,
and a text-to-SQL copilot.

- **Extraction**: messy invoice PDFs to validated, structured data, with a human review queue
- **Warehouse**: SAP-style staging and marts with dbt + DuckDB
- **Quality agent**: three-way match, duplicates, anomalies, root-cause explanations, proposed tests
- **Analytics copilot**: text-to-SQL over a semantic layer, with a golden-set evaluation

Every stage is measured. Results go here as they are produced.

## Status

Work in progress. See [TODO.md](TODO.md).

| Component | Status |
|---|---|
| Synthetic data generator (master data, POs, goods receipts, invoices) | Done |
| Error injection and answer-key manifest | Done |
| PDF degradation (scan noise, skew, low resolution) | Done |
| Extraction, warehouse, quality agent, copilot | Not started |

## Quickstart

```bash
make setup
make test
make data       # writes CSVs and invoice PDFs to data/generated/
make hello-llm
```

## Synthetic data

There is no real SAP data, so the project generates its own. Everything is deterministic:
the same seed gives the same files.

With seed 42 the generator produces 40 vendors, 120 materials, 200 purchase orders
(609 lines), 683 goods receipts, and 206 invoice PDFs.

- **Clean SAP side**: `vendors.csv`, `materials.csv`, `po_headers.csv`, `po_lines.csv`,
  `goods_receipts.csv`. These are the source of truth and never contain errors.
- **Invoice side**: `invoices.csv`, `invoice_lines.csv` and the PDFs. The CSVs hold exactly what
  is printed on each PDF, errors included, so they are the ground truth for the extraction eval.
- **Answer key**: `error_manifest.csv` lists which invoice carries which error. It is the
  ground truth for the quality-agent eval.
- **Layouts**: invoices come in several languages (English, French, Italian), number formats
  (`1,234.50`, `1 234,50`, `1.234,50`), fonts and table styles.

### Injected errors

20% of the invoices carry one error each. The rates are set in `src/p2p/data_gen/errors.py`.

| Error type | Share | Subtypes |
|---|---|---|
| `duplicate_invoice` | 3% | `exact_copy`, `reformatted_number`, `renumbered` |
| `price_variance` | 4% | `over`, `under` |
| `quantity_mismatch` | 4% | `over`, `under` |
| `line_sum_mismatch` | 2% | `total_off`, `line_amount_off` |
| `po_reference` | 3% | `missing`, `nonexistent`, `other_vendor` |
| `vat_currency` | 2% | `wrong_vat`, `wrong_currency` |
| `invoice_before_gr` | 2% | none |

Duplicates are added as new invoices (`INV000201` to `INV000206`), so 200 clean invoices become
206 PDFs. A price or quantity change recomputes the invoice's own totals, so only a comparison
with the PO or goods receipt exposes it. `line_sum_mismatch` is the one type that breaks the
invoice's own arithmetic.

### How the data is checked

`tests/test_errors.py` runs seven independent rule checks without reading the manifest. The test
passes only if every injected invoice trips exactly its own check and no clean invoice trips any.
Another test renders all PDFs, and a guard shrinks or rejects any table header that does not fit
its column.

Load the manifest with `pd.read_csv(..., dtype=str, keep_default_na=False)`, so an empty
`invoice_value` stays an empty string instead of becoming `NaN`.

## Results

Coming soon.

## Design decisions

- **One error per invoice.** Each finding maps to exactly one expected answer, so scoring is
  unambiguous.
- **Errors only on the invoice side.** POs and goods receipts stay clean because they model SAP,
  which is the reference the agent compares against.
- **Rule-based cross-check of the manifest.** The answer key is verified by independent code, so
  the manifest and the data cannot drift apart.

More to come as the other stages land.

## Limitations

- **Error rate is unrealistic.** 20% of invoices carry an error. Real AP rates are much lower.
  The high rate gives the evals enough positive cases.
- **No same-vendor wrong PO.** The `other_vendor` cases point to a PO of a different vendor.
  An invoice that cites another PO of the same vendor is not generated, because it is invisible
  without comparing line items.
- **Duplicates flag the later copy only.** The manifest marks the copy and points to the original
  in `related_invoice_id`. An agent that flags the original instead is scored as wrong.
- **Synthetic documents.** Invoices are clean, generated PDFs with a small set of layouts. They
  are not yet degraded like real scans. Tax IDs are not in real national formats.
- **Small sample.** With 200 invoices, some error subtypes have only 2 cases, so per-subtype
  scores are noisy.
