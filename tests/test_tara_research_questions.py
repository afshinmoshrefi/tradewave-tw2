"""Michael's 20 research prompts must retrieve actionable, truthful guidance."""
import json
from pathlib import Path
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver/appserver"))
from tara_prompt_context import (parse_knowledge_sections, select_topic_knowledge,
    needs_yearly_results, MAX_TOPIC_KNOWLEDGE_CHARS, MAX_TOPIC_SECTIONS)
CASES = json.loads((ROOT / "tests/fixtures/tara_research_questions.json").read_text())
KB = (ROOT / "appserver/appserver/chatbot_knowledge.txt").read_text()
SECTIONS = parse_knowledge_sections(KB)

@pytest.mark.parametrize("case", CASES, ids=lambda c: str(c["id"]))
@pytest.mark.parametrize("form", ["template", "concrete"])
def test_research_question_retrieves_its_workflow(case, form):
    chosen = select_topic_knowledge(case[form], SECTIONS)
    assert chosen.headings[0] == case["section"]
    assert "The 100-Year Pattern" not in chosen.headings
    assert len(chosen.headings) <= MAX_TOPIC_SECTIONS
    assert len(chosen.text) <= MAX_TOPIC_KNOWLEDGE_CHARS + 200
    assert case["template"] in chosen.text

@pytest.mark.parametrize("question", [
    "Show me the exact years that AAPL's January bullish pattern failed and how much it lost.",
    "Which years did this window lose money?",
])
def test_failure_year_requests_include_actual_yearly_receipts(question):
    assert needs_yearly_results(question)

@pytest.mark.parametrize("question", [
    "What is a seasonal pattern?", "What is the 100-Year Pattern?",
    "Explain Sharpe ratio", "How do I create a watchlist?", "What are calendar days?",
])
def test_research_routes_do_not_displace_basic_product_questions(question):
    chosen = select_topic_knowledge(question, SECTIONS)
    assert not any(h.startswith("Research Requests:") for h in chosen.headings)

@pytest.mark.parametrize("question, required", [
    ("Explain the 100-Year Pattern", "The 100-Year Pattern"),
    ("What is the opportunity table?", "The Opportunity Table (Left Panel)"),
    ("What does Compare Symbols do?", "Interactive Analysis Reports"),
])
def test_existing_named_features_remain_reachable(question, required):
    assert required in select_topic_knowledge(question, SECTIONS).headings


def test_corpus_preserves_all_twenty_source_questions():
    assert [c["id"] for c in CASES] == list(range(1, 21))
    assert "15 trading days" in CASES[7]["template"]
    assert "45-day hold" in CASES[3]["template"]
