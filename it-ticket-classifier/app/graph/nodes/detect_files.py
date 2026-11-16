from app.graph.state import AgentState
from app.parsers.registry import category_for_filename, parser_kind_for_file


def detect_attachments(state: AgentState) -> dict:
    attachments = state.get("attachments") or []
    branches = {
        "text": bool((state.get("description") or "").strip()),
        "docs": False,
        "images": False,
        "diagrams": False,
    }

    for att in attachments:
        cat = category_for_filename(att["filename"])
        kind = parser_kind_for_file(att["filename"])
        if cat in ("document", "presentation", "spreadsheet") and cat != "image":
            if att["filename"].lower().endswith(".csv") or cat == "spreadsheet":
                branches["docs"] = True
            else:
                branches["docs"] = True
        elif cat == "image":
            branches["images"] = True
        elif cat == "diagram":
            branches["diagrams"] = True
        elif cat in ("text", "structured") or kind is not None:
            branches["docs"] = True

    return {"branches": branches}