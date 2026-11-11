import pytest

from pharma_dates.taxonomy import ALL_TYPES, FAMILIES, as_json, family_of, offline_label

# Spec §6, copied by hand so a change to the module has to be a change to the spec too.
SPEC_TYPES = {
    "product": [
        "manufacture_date",
        "expiry_date",
        "retest_date",
        "packaging_date",
        "release_date",
        "sampling_date",
        "test_date",
        "analysis_report_date",
    ],
    "document": [
        "effective_date",
        "issue_date",
        "version_date",
        "approval_date",
        "review_date",
        "next_review_date",
        "superseded_date",
    ],
    "signature": ["signature_date"],
    "legal": [
        "certificate_issue_date",
        "certificate_valid_until",
        "notarization_date",
        "apostille_date",
        "legalization_date",
        "translation_certification_date",
        "authorization_date",
    ],
    "audit": ["inspection_date", "audit_date", "next_audit_date", "capa_due_date"],
    "logistics": ["shipping_date", "receipt_date"],
    "other": ["other_date", "unknown"],
}


def test_every_spec_type_present():
    expected = {t for types in SPEC_TYPES.values() for t in types}
    assert len(expected) == 31
    assert ALL_TYPES == expected
    assert {
        "apostille_date",
        "certificate_valid_until",
        "signature_date",
        "retest_date",
        "unknown",
    } <= ALL_TYPES
    assert FAMILIES == SPEC_TYPES


def test_family_of():
    assert family_of("notarization_date") == "legal"
    assert family_of("expiry_date") == "product"
    assert family_of("unknown") == "other"


def test_family_of_unknown_type_raises():
    with pytest.raises(KeyError):
        family_of("birthday")


def test_as_json_covers_every_type_once():
    data = as_json()
    assert [family["family"] for family in data] == list(SPEC_TYPES)
    ids = [t["id"] for family in data for t in family["types"]]
    assert sorted(ids) == sorted(ALL_TYPES)
    assert all(family["label"] and all(t["label"] for t in family["types"]) for family in data)
    by_id = {t["id"]: t["label"] for family in data for t in family["types"]}
    assert by_id["capa_due_date"] == "CAPA due date"
    assert by_id["certificate_valid_until"] == "Certificate valid until"
    assert by_id["expiry_date"] == "Expiry date"


@pytest.mark.parametrize(
    ("rule_label", "context", "expected"),
    [
        ("expiry", "...", "expiry_date"),
        ("manufacture", "MFG 01/2026", "manufacture_date"),
        ("audit", "Audit performed", "audit_date"),
        ("received", "Received on", "receipt_date"),
        ("document", "Report date", "issue_date"),
        ("document", "Signed by J. Doe on", "signature_date"),
        ("document", "Apostille ... date", "apostille_date"),
        ("document", "Notarized before me on", "notarization_date"),
        ("document", "Effective date:", "effective_date"),
        ("qa_check", "Approved by QA", "approval_date"),
        ("unknown", "Re-test date", "retest_date"),
        ("unknown", "Retest by", "retest_date"),
        ("qa_check", "", "unknown"),
        ("unknown", "Lot 42", "unknown"),
        ("not_a_rule_label", "", "unknown"),
    ],
)
def test_offline_label(rule_label, context, expected):
    assert offline_label(rule_label, context) == expected


def test_offline_label_certificate_validity_refines_expiry():
    assert offline_label("expiry", "GMP Certificate valid until") == "certificate_valid_until"
    # A certificate of analysis lists the product's expiry; that stays an expiry date.
    assert offline_label("expiry", "Certificate of Analysis. Expiry date:") == "expiry_date"


def test_offline_label_apostille_beats_its_own_signature_wording():
    assert offline_label("document", "Apostille. This public document has been signed by") == "apostille_date"


def test_offline_label_always_in_taxonomy():
    for rule_label in ["expiry", "manufacture", "qa_check", "audit", "received", "document", "unknown"]:
        assert offline_label(rule_label, "signed approved effective retest") in ALL_TYPES


def test_offline_label_reads_only_the_dates_line():
    text = "CERTIFICATE OF ANALYSIS\nExpiry date: 31-Jan-2025\nThis certificate is valid without signature."
    start = text.index("31-Jan")
    assert offline_label("expiry", text, start, start + 11) == "expiry_date"
    text = "Signed by J. Doe\nIssued: 05-Jan-2026"
    start = text.index("05-Jan")
    assert offline_label("document", text, start, start + 11) == "issue_date"


def test_offline_label_nearest_keyword_wins():
    text = "Approved by J. Doe   Signature: ____ 05-Jan-2026"
    start = text.index("05-Jan")
    assert offline_label("qa_check", text, start, start + 11) == "signature_date"
    text = "Signed by J. Doe. Effective date: 05-Jan-2026"
    start = text.index("05-Jan")
    assert offline_label("unknown", text, start, start + 11) == "effective_date"


def test_offline_label_bare_row_reads_its_heading_but_not_past_another_date():
    text = "APOSTILLE\nIssued by the competent authority\n6. the 12 March 2026"
    start = text.index("12 March")
    assert offline_label("unknown", text, start, start + 13) == "apostille_date"
    text = "Signature: ____\nTested: 01-Jan-2026\nDate: 05-Jan-2026"
    start = text.index("05-Jan")
    assert offline_label("unknown", text, start, start + 11) == "unknown"
    text = "Signature: ____\nAnalysis date: 07-Jan-2026"
    start = text.index("07-Jan")
    assert offline_label("unknown", text, start, start + 11) == "unknown"


def test_offline_label_wrapped_sentence_reads_the_line_above():
    text = "Expiration of Certification: The certification of SRM 870 is valid, within the\nuntil 31 December 2035"
    start = text.index("31 December")
    assert offline_label("unknown", text, start, start + 16) == "certificate_valid_until"


def test_offline_label_revision_row_is_not_a_bare_row():
    text = "Approved by L. Brennan\nRevision history\n1.0 12.Jun.2018 First issue"
    start = text.index("12.Jun")
    assert offline_label("unknown", text, start, start + 11) == "unknown"
