"""Tiny import + i18n smoke tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_import_all():
    import interview_assistant
    from interview_assistant import (
        config, providers, stt_filter, homophones, skills,
        rag, qa, theme, i18n, knowledge_tools, doctor, cli, init_wizard,
    )
    assert interview_assistant.__version__


def test_i18n_zh_en():
    from interview_assistant import i18n
    i18n.set_language("zh-CN")
    assert "面试" in i18n.t("app.name")
    i18n.set_language("en")
    assert "Interview" in i18n.t("app.name")


def test_stt_filter():
    from interview_assistant.stt_filter import STTFilter
    f = STTFilter()
    assert f.is_hallucination("感谢观看")
    assert f.is_hallucination("悠悠独播剧场")
    assert f.is_filler("OK")
    assert f.is_filler("嗯嗯")
    assert not f.is_hallucination("Tell me about yourself")


def test_skill_discovery():
    from interview_assistant import skills
    bundled = skills.bundled_skills_dir()
    assert bundled.is_dir(), f"bundled skills not found at {bundled}"
    sks = skills.discover([])
    names = {s.name for s in sks}
    assert "interview-knowledge-format" in names
    assert "homophone-detector" in names


def test_skill_runtime_hooks():
    from interview_assistant import skills, stt_filter, homophones
    sks = skills.discover([])
    summary = skills.apply_runtime_hooks(sks)
    assert any("hallucinations" in entry[1] for entry in summary["loaded"])
    assert any("homophones" in entry[1] for entry in summary["loaded"])
    f = stt_filter.STTFilter(extra_hallucinations=summary["extra_hallucinations"])
    assert f.is_hallucination("悠悠独播剧场")


def test_config_defaults():
    from interview_assistant import config
    cfg = config.DEFAULTS
    assert "ui" in cfg and "stt" in cfg and "chat" in cfg
    assert cfg["hotkey"]["ptt"] == "alt_r"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  OK  {name}")
