from backend.app.workflow import ComicWorkflow


def test_entry_routes_by_persisted_stage():
    assert ComicWorkflow._entry_route({"stage": "brief"}) == "pm"
    assert ComicWorkflow._entry_route({"stage": "script"}) == "consultants"
    assert ComicWorkflow._entry_route({"stage": "character_design"}) == "designer"
    assert ComicWorkflow._entry_route({"stage": "illustration"}) == "artist"
    assert ComicWorkflow._entry_route({"stage": "review"}) == "editor"


def test_editor_routes_revision_to_owner():
    assert ComicWorkflow._after_editor({"stage": "script"}) == "writer"
    assert ComicWorkflow._after_editor({"stage": "character_design"}) == "designer"
    assert ComicWorkflow._after_editor({"stage": "illustration"}) == "artist"
    assert ComicWorkflow._after_editor({"stage": "layout"}) == "editor"
    assert ComicWorkflow._after_editor({"stage": "finalized"}) == "pm"

