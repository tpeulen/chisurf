"""ZMQ RPC handlers for the Help plugin."""

from __future__ import annotations

import logging
from typing import Any

from chisurf.plugins.core.help.api import review
from chisurf.plugins.core.help.api.contract import (
    METHOD_ASK,
    METHOD_CONTRACT,
    METHOD_LIST_DOCS,
    METHOD_READ_DOC,
    METHOD_REVIEW_CHECK,
    METHOD_REVIEW_SET,
    METHOD_REVIEW_STATUS,
    METHOD_SAVE_DOC,
    METHOD_SEARCH_DOCS,
    contract_descriptor,
    service_error,
    service_success,
)
from chisurf.plugins.core.help.api.io import (
    discover_docs,
    read_doc,
    save_doc,
    search_docs,
)
from chisurf.plugins.core.help.api.render import document_title, render_document

_log = logging.getLogger(__name__)


def _list_docs_handler() -> dict:
    try:
        info = discover_docs()
        results = [
            {
                "path": e.path,
                "title": e.title,
                "category": e.category,
                "file_name": e.file_name,
                "size": e.size,
                "review_status": e.review_status,
                "reviewer": e.reviewer,
                "review_date": e.review_date,
            }
            for e in info.entries
        ]
        return service_success({"entries": results, "tree": info.tree})
    except Exception as exc:
        _log.exception("help.docs.list failed")
        return service_error(str(exc), "LIST_FAILED")


def _read_doc_handler(params: dict) -> dict:
    path = params.get("path", "")
    if not path:
        return service_error("path is required", "INVALID_PARAMS")
    try:
        content = read_doc(path)
        if content is None:
            return service_error(f"cannot read {path}", "READ_FAILED")
        html = render_document(content, path)
        title = document_title(content, path) or path
        status = review.status_of(path)
        return service_success(
            {
                "content": content,
                "html": html,
                "title": title,
                "review_status": status.status,
                "reviewer": status.reviewer,
                "review_date": status.date,
            }
        )
    except Exception as exc:
        _log.exception("help.docs.read failed")
        return service_error(str(exc), "READ_FAILED")


def _save_doc_handler(params: dict) -> dict:
    path = params.get("path", "")
    content = params.get("content", "")
    if not path or content is None:
        return service_error("path and content are required", "INVALID_PARAMS")
    try:
        ok = save_doc(path, content)
        if not ok:
            return service_error(f"cannot save {path}", "SAVE_FAILED")
        return service_success({"path": path})
    except Exception as exc:
        _log.exception("help.docs.save failed")
        return service_error(str(exc), "SAVE_FAILED")


def _search_docs_handler(params: dict) -> dict:
    query = params.get("query", "")
    if not query:
        return service_error("query is required", "INVALID_PARAMS")
    try:
        results = search_docs(query)
        return service_success(results)
    except Exception as exc:
        _log.exception("help.docs.search failed")
        return service_error(str(exc), "SEARCH_FAILED")


def _review_status_handler(params: dict) -> dict:
    path = params.get("path", "")
    if not path:
        return service_error("path is required", "INVALID_PARAMS")
    try:
        status = review.status_of(path)
        return service_success(
            {
                "path": status.path,
                "rel_path": status.rel_path,
                "status": status.status,
                "reviewer": status.reviewer,
                "reviewer_kind": status.reviewer_kind,
                "previous_status": status.previous_status,
                "date": status.date,
                "tracked": review.is_tracked(path),
            }
        )
    except Exception as exc:
        _log.exception("help.review.status failed")
        return service_error(str(exc), "REVIEW_FAILED")


def _review_set_handler(params: dict) -> dict:
    path = params.get("path", "")
    status = params.get("status", "")
    reviewer = params.get("reviewer", "")
    reviewer_kind = params.get("reviewer_kind", "")
    allowed = (
        review.STATUS_REVIEWED,
        review.STATUS_AI_REVIEWED,
        review.STATUS_UNREVIEWED,
    )
    if not path or status not in allowed:
        return service_error(
            "path and status ('reviewed', 'ai-reviewed' or 'unreviewed') are required",
            "INVALID_PARAMS",
        )
    try:
        if not review.is_tracked(path):
            return service_error(f"{path} is not review-tracked", "NOT_TRACKED")
        if not review.set_status(path, status, reviewer, reviewer_kind):
            return service_error(f"cannot record status for {path}", "REVIEW_FAILED")
        new_status = review.status_of(path)
        return service_success(
            {
                "path": new_status.path,
                "status": new_status.status,
                "reviewer": new_status.reviewer,
                "reviewer_kind": new_status.reviewer_kind,
                "date": new_status.date,
            }
        )
    except Exception as exc:
        _log.exception("help.review.set failed")
        return service_error(str(exc), "REVIEW_FAILED")


def _review_check_handler() -> dict:
    try:
        report = review.scan()
        return service_success(
            {
                "passed": report.ok,
                "summary": report.summary(),
                "counts": {
                    "reviewed": len(report.reviewed),
                    "ai_reviewed": len(report.ai_reviewed),
                    "stale": len(report.stale),
                    "unreviewed": len(report.unreviewed),
                    "tracked": len(report.pages),
                },
                "blocking": [
                    {"rel_path": p.rel_path, "status": p.status, "path": p.path}
                    for p in report.blocking
                ],
            }
        )
    except Exception as exc:
        _log.exception("help.review.check failed")
        return service_error(str(exc), "REVIEW_FAILED")


def _ask_handler(params: dict) -> dict:
    """Answer a question out of the documentation.

    The heavy part — a language-model round trip and several page reads — runs
    on the backend, so the GUI client stays a thin caller and the same answer
    is reachable from the CLI and from a script.
    """
    question = (params or {}).get("question", "")
    if not question:
        return service_error("question is required", "INVALID_PARAMS")
    try:
        from chisurf.plugins.core.help.api import ask as ask_api

        answer = ask_api.ask(
            question,
            model=(params or {}).get("model", ""),
            provider=(params or {}).get("provider", ""),
        )
        return service_success(answer.to_dict())
    except Exception as exc:
        _log.exception("help.docs.ask failed")
        return service_error(str(exc), "ASK_FAILED")


def _contract_handler() -> dict:
    return service_success(contract_descriptor())


def register_services(dispatcher: Any) -> None:
    """Register all Help plugin RPC handlers with a ServiceDispatcher.

    Parameters
    ----------
    dispatcher : ServiceDispatcher
        The server's service dispatcher instance.

    """
    dispatcher.register(METHOD_LIST_DOCS, lambda params: _list_docs_handler())
    dispatcher.register(METHOD_READ_DOC, _read_doc_handler)
    dispatcher.register(METHOD_SAVE_DOC, _save_doc_handler)
    dispatcher.register(METHOD_SEARCH_DOCS, _search_docs_handler)
    dispatcher.register(METHOD_ASK, _ask_handler)
    dispatcher.register(METHOD_CONTRACT, lambda params: _contract_handler())
    dispatcher.register(METHOD_REVIEW_STATUS, _review_status_handler)
    dispatcher.register(METHOD_REVIEW_SET, _review_set_handler)
    dispatcher.register(METHOD_REVIEW_CHECK, lambda params: _review_check_handler())

    # Legacy aliases for backward compatibility
    dispatcher.register("help.list_docs", lambda params: _list_docs_handler())
    dispatcher.register("help.read_doc", _read_doc_handler)
    dispatcher.register("help.save_doc", _save_doc_handler)

    _log.info("Registered Help plugin services")
