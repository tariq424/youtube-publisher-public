import publisher_logic as logic


def test_short_without_placeholder_gets_link_when_explainer_exists(monkeypatch):
    monkeypatch.setattr(logic, "has_long", lambda job: True)
    monkeypatch.setattr(logic, "long_record", lambda c, j: None)
    d, st = logic.link_short("j1", "yousocial", "Short text.\n#tags", "https://youtu.be/x")
    assert st == "linked" and d.endswith("Full breakdown: https://youtu.be/x\n")
    monkeypatch.setattr(logic, "has_long", lambda job: False)
    assert logic.link_short("j1", "yousocial", "Short text.", None) == ("Short text.", "none")
