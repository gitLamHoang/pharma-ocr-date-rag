from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_demo_library_filters_and_empty_search():
    app = AppTest.from_file(str(ROOT / "demo_app.py"), default_timeout=20).run()
    assert not app.exception
    assert app.metric[0].value == "8"
    assert app.metric[1].value == "42"
    app.selectbox(key="collection").select("French").run()
    assert not app.exception
    assert app.metric[0].value == "1"
    assert app.metric[1].value == "6"
    app.checkbox(key="only_review").check().run()
    assert len(app.dataframe[0].value) == 1
    app.text_input(key="question").set_value("astronomy").run()
    assert any(item.value == "No matching evidence found." for item in app.info)


def test_paste_flow_resolves_an_explicit_date_convention():
    app = AppTest.from_file(str(ROOT / "demo_app.py"), default_timeout=20).run()
    app.radio(key="source").set_value("Paste text").run()
    app.text_area(key="document_text").set_value("Date de péremption: 09/10/2026").run()
    assert not app.exception
    assert app.metric[3].value == "1"
    app.selectbox(key="date_order").select("dmy").run()
    assert not app.exception
    assert app.metric[3].value == "0"
    assert app.dataframe[0].value.iloc[0]["Date"] == "2026-10-09"


def test_document_conventions_persist_across_selection_and_collection_changes():
    app = AppTest.from_file(str(ROOT / "demo_app.py"), default_timeout=20).run()
    app.selectbox(key="collection").select("Mixed conventions").run()
    assert app.metric[0].value == "3"
    assert app.metric[3].value == "5"
    for name, order in [
        ("eu_receipt.txt", "dmy"),
        ("us_receipt.txt", "mdy"),
        ("unconfirmed_receipt.txt", "auto"),
    ]:
        app.selectbox(key="policy_document").select(name).run()
        app.selectbox(key=f"document_order_choice_{name}").select(order).run()
    assert not app.exception
    assert app.metric[3].value == "1"
    app.selectbox(key="date_order").select("mdy").run()
    assert app.metric[3].value == "1"  # Explicit auto must not inherit a resolved global policy.
    table = app.dataframe[0].value
    expiry = table[table["Type"] == "expiry"].set_index("Document")
    assert expiry.loc["eu_receipt.txt"]["Date"] == "2026-10-09"
    assert expiry.loc["us_receipt.txt"]["Date"] == "2026-09-10"
    app.selectbox(key="policy_document").select("eu_receipt.txt").run()
    assert app.selectbox(key="document_order_choice_eu_receipt.txt").value == "dmy"
    app.selectbox(key="collection").select("French").run()
    app.selectbox(key="collection").select("Mixed conventions").run()
    assert not app.exception
    assert app.metric[3].value == "1"
    app.selectbox(key="date_order").select("auto").run()
    app.button[0].click().run()
    assert not app.exception
    assert app.metric[3].value == "5"
    assert app.session_state["document_orders"] == {}
