#!/usr/bin/env python3
# app.py - Web dashboard for the Gateway Serial Test Framework
#
# Wraps the existing, already-tested logic in add_test_agent.py and
# ai_test_agent.py behind a small local Flask API, and serves a single-page
# dashboard. Nothing about the underlying test-generation logic changes -
# this is a UI layer, not a rewrite.
#
# Run:   python app.py
# Open:  http://127.0.0.1:5000

from flask import Flask, jsonify, request, render_template

import tests as tests_module
from add_test_agent import (
    to_snake_case,
    existing_registration_keys,
    generate_code,
    append_to_file,
)
from ai_test_agent import call_groq_extract, explain_testcase, build_fallback_summary

# Import custom_tests.py if it exists so previously-added tests show up
try:
    import custom_tests  # noqa: F401
except ImportError:
    pass

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", active="dashboard")


@app.route("/add/manual")
def add_manual():
    return render_template("manual.html", active="manual")


@app.route("/add/ai")
def add_ai():
    return render_template("ai.html", active="ai")


@app.route("/api/suites")
def api_suites():
    """List every registered test suite (built-in + custom)."""
    suites = []
    for key, suite in tests_module.TEST_SUITES.items():
        suites.append({
            "key": key,
            "name": suite.name,
            "description": suite.description,
            "test_count": len(suite.tests),
            "test_names": [t.name for t in suite.tests],
            "tests": [
                {"name": t.name, "command": t.command, "timeout": t.timeout}
                for t in suite.tests
            ],
        })
    suites.sort(key=lambda s: s["key"])
    return jsonify({"suites": suites, "total": len(suites)})


@app.route("/api/extract", methods=["POST"])
def api_extract():
    """AI extraction only - does not write anything."""
    data = request.get_json(force=True)
    user_text = (data.get("description") or "").strip()

    if not user_text:
        return jsonify({"ok": False, "error": "Description cannot be empty."}), 400

    extracted = call_groq_extract(user_text)

    if extracted is None:
        return jsonify({
            "ok": False,
            "error": "AI extraction unavailable (missing GROQ_API_KEY, network "
                     "issue, or the API rejected the request). Use manual mode "
                     "instead.",
        }), 502

    return jsonify({"ok": True, "fields": extracted})


@app.route("/api/explain", methods=["POST"])
def api_explain():
    """Reverse mode: given a suite key + test name, ask the AI to explain
    what that existing TestCase does in plain English."""
    data = request.get_json(force=True)
    suite_key = (data.get("suite_key") or "").strip()
    test_name = (data.get("test_name") or "").strip()

    suite = tests_module.TEST_SUITES.get(suite_key)
    if suite is None:
        return jsonify({"ok": False, "error": f'No suite registered as "{suite_key}".'}), 404

    testcase = next((t for t in suite.tests if t.name == test_name), None)
    if testcase is None:
        return jsonify({"ok": False, "error": f'No test named "{test_name}" in that suite.'}), 404

    explanation = explain_testcase(testcase)
    if explanation is None:
        return jsonify({
            "ok": False,
            "error": "AI explanation unavailable (missing GROQ_API_KEY, network "
                     "issue, or the API rejected the request).",
        }), 502

    return jsonify({"ok": True, "explanation": explanation, "test_name": test_name})


@app.route("/api/check-key", methods=["POST"])
def api_check_key():
    """Check whether a registration key is already taken."""
    data = request.get_json(force=True)
    key = (data.get("key") or "").strip()
    taken = key in existing_registration_keys()
    return jsonify({"key": key, "taken": taken})


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """Build the generated code preview from fully-specified fields.
    Does not write to disk."""
    data = request.get_json(force=True)

    name = to_snake_case((data.get("name") or "").strip())
    command = (data.get("command") or "").strip()
    description = (data.get("description") or "").strip() or f"Run {name}"
    try:
        timeout = int(data.get("timeout") or 5)
    except (ValueError, TypeError):
        timeout = 5
    expected_output = (data.get("expected_output") or "").strip() or None
    validate_func = (data.get("validate_func") or "").strip() or None
    summary = (data.get("summary") or "").strip() or None
    # Mutually exclusive - validator wins, same rule as the CLI agent
    if validate_func:
        expected_output = None
    if not summary:
        summary = build_fallback_summary({
            "command": command,
            "expected_output": expected_output,
            "validate_func": validate_func,
        })

    if not name or not command:
        return jsonify({"ok": False, "error": "Test name and command are required."}), 400
    if timeout <= 0:
        return jsonify({"ok": False, "error": "Timeout must be a positive integer."}), 400

    suite_name = (data.get("suite_name") or "").strip() or name
    suite_description = (data.get("suite_description") or "").strip() or description
    key = (data.get("registration_key") or "").strip() or suite_name

    testcase = {
        "name": name,
        "command": command,
        "description": description,
        "summary": summary,
        "timeout": timeout,
        "expected_output": expected_output,
        "validate_func": validate_func,
    }
    suite = {"name": suite_name, "description": suite_description}

    code = generate_code(testcase, suite, key)
    key_taken = key in existing_registration_keys()

    return jsonify({
        "ok": True,
        "code": code,
        "summary": summary,
        "registration_key": key,
        "key_taken": key_taken,
        "normalized_name": name,
    })


@app.route("/api/save", methods=["POST"])
def api_save():
    """Write previously-previewed code to custom_tests.py."""
    data = request.get_json(force=True)
    code = data.get("code", "")
    key = (data.get("registration_key") or "").strip()
    force_overwrite = bool(data.get("force_overwrite"))

    if not code.strip():
        return jsonify({"ok": False, "error": "No code to save - build a preview first."}), 400

    if key in existing_registration_keys() and not force_overwrite:
        return jsonify({
            "ok": False,
            "error": f'TEST_SUITES["{key}"] already exists. Choose a different '
                     f"key or confirm overwrite.",
            "duplicate": True,
        }), 409

    success = append_to_file(code)
    if not success:
        return jsonify({"ok": False, "error": "Write succeeded but custom_tests.py "
                                               "failed to compile. Check the file."}), 500

    return jsonify({"ok": True, "message": f'Test registered as "{key}".'})


if __name__ == "__main__":
    print("=" * 60)
    print("Gateway Serial Test Framework - Web Dashboard")
    print("=" * 60)
    print("Open http://127.0.0.1:5000 in your browser")
    print("Press CTRL+C to stop")
    # custom_tests.py is generated output, not app source - exclude it from
    # the debug reloader's watch list so saving a test doesn't restart the
    # server mid-request (which was dropping the browser's connection).
    app.run(
        debug=True,
        port=5000,
        exclude_patterns=["*custom_tests.py"],
    )

