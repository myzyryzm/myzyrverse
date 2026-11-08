import pytest

from backend import config


@pytest.fixture(autouse=True)
def tmp_project(tmp_path, monkeypatch):
    """Point every path in config at a throwaway directory and force fake LLM output."""
    lore = tmp_path / "lore"
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "LORE_DIR", lore)
    monkeypatch.setattr(config, "PREHISTORY_DIR", lore / "prehistory")
    monkeypatch.setattr(config, "SOURCES_DIR", lore / "sources")
    monkeypatch.setattr(config, "OPEN_QUESTIONS_FILE", lore / "open_questions.json")
    monkeypatch.setattr(config, "EVENTS_FILE", lore / "events.json")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "MANUSCRIPT_FILE", tmp_path / "manuscript.md")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CHECKPOINT_DB", tmp_path / "data" / "checkpoints.sqlite")
    monkeypatch.setattr(config, "FAKE_LLM", True)
    (lore / "prehistory").mkdir(parents=True)
    (lore / "prehistory" / "world.md").write_text("Egypt, 1160 BCE. Tiye plots.")
    return tmp_path
