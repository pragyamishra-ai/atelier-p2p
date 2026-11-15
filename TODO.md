# TODO (update at the end of every session)

## Next task (start here tomorrow)
- [ ] Commit the scan fixes if not already pushed (specks skip ink, `Prix` header, softer bad profile)
- [ ] Run `grep -c 4500000000 data/generated/po_headers.csv`. It should print 1 or more. A 0 means
      an invoice cites a PO that does not exist and is not in the `nonexistent` error set (bug).
- [ ] Check that `INV000004` and `INV000113` (both number `2026/00750`) have different `vendor_id`s.
      The same vendor would be an unlabelled duplicate (generator bug).
- [ ] Re-open `INV000004.pdf` (Courier, bad scan). `Prix (EUR)`, `167`, `77,02` and `6 297,57`
      should be readable, and no speck should touch a digit or table line.
      If still ambiguous, raise the bad `dpi` to `(130, 150)`.
- [ ] Open a serif (Times) invoice from a German, UK or US vendor. Check layout, header fit and
      stamp position. It is the only layout not seen yet.
- [ ] Add your API key to .env and run `make hello-llm`
- [ ] Decide the model or API for extraction (vision-capable, because 60% of PDFs are scans)

## Backlog
- [ ] Test that no speck lands on ink, so the speck rule cannot regress silently
- [ ] README: add `invoice_meta.csv`, the 40/35/25 clean/mild/bad split, and the folders
      `invoices_clean/` and `invoices/`
- [ ] README limitations: scans are simulated (no folds, shadows or scanner artifacts), specks never
      touch ink, and the bad tier needs a calibration check in step 6
- [ ] Week 4-6: extraction pipeline
  - [ ] Text path for clean PDFs, vision path for scans
  - [ ] Read `data/generated/invoices/`, score against `invoices.csv` and `invoice_lines.csv`
  - [ ] Split every metric by `scan_quality`
  - [ ] Calibration: if the best model scores far lower on bad than on mild, read its errors to see
        whether the cause is the model or an unreadable value
  - [ ] Validation rules and a human review queue for low-confidence extractions
- [ ] Quality agent: score against `error_manifest.csv`
      (load with `dtype=str, keep_default_na=False`)
- [ ] Optional: wrong-PO case that cites another PO of the same vendor
- [ ] Optional: lower the error rate (currently 20%) for a more realistic secondary eval

## Done
- [x] Generator step 1-3: master data, POs, goods receipts, clean invoice PDFs (3 layouts)
- [x] Generator step 4: error injection and `error_manifest.csv` (40 errors, 7 types)
- [x] Header-fit guard so table headers never overflow their columns
- [x] Generator step 5: scan degradation, 40% clean / 35% mild / 25% bad, `invoice_meta.csv`
- [x] README: synthetic data section, error spec, limitations
