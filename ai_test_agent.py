#!/usr/bin/env python3
# ai_test_agent.py - AI-Assisted TestCase extraction (--add-test-ai)
#
# Adds a natural-language front-end on top of the existing, already-tested
# add_test_agent.py pipeline. The LLM only extracts structured fields from
# what the user describes - it never invents gateway-specific commands.
# Every extracted field is shown to the user for confirmation/override
# before the same generate_code() / append_to_file() safety net runs.
#
# Requires a free Groq API key (https://console.groq.com) set as the
# GROQ_API_KEY environment variable. If it's missing or the call fails,
# this falls back to the plain manual flow automatically - --add-test-ai
# never crashes just because the AI step failed.


import json
import urllib.request
import urllib.error
import os
from dotenv import load_dotenv

load_dotenv()

from add_test_agent import (
    to_snake_case,
    collect_testcase,
    collect_testsuite,
    collect_registration,
    generate_code,
    append_to_file,
    CUSTOM_TESTS_FILE,
)


api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

print("API key loaded:", api_key is not None)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

EXTRACTION_SYSTEM_PROMPT = """
You convert a plain-English description of a gateway test into JSON.

Return ONLY valid JSON.
Do not return prose.
Do not return markdown code fences.

Use exactly this schema:

{
    "name": "snake_case_test_name, or null if not clear",
    "command": "the exact shell command mentioned by the user, or null if none was given",
    "summary": "one short sentence explaining what the test verifies",
    "description": "one-line description of the test, or null",
    "timeout": "integer seconds, or null",
    "expected_output": "a single substring to check for, or null",
    "validate_func": "a Python boolean expression on variable o, or null"
}

Rules:

- ALWAYS generate a summary.
- The summary must be one short sentence.
- Maximum 20 words.
- Explain what the test verifies.
- Do not repeat the command.
- Never return summary as null.
"""

def get_grounding_examples(n=6):
    """Pull a handful of real TestCase examples straight from tests.py,
    so the AI sees actual command syntax used in this codebase instead
    of guessing blind. Returns a formatted string block for the prompt."""
    import tests as tests_module

    examples = []
    seen_commands = set()
    for suite in tests_module.TEST_SUITES.values():
        for tc in suite.tests:
            if tc.command in seen_commands:
                continue
            seen_commands.add(tc.command)
            line = f'- command: {tc.command!r}  ->  description: "{tc.description}"'
            examples.append(line)
            if len(examples) >= n:
                break
        if len(examples) >= n:
            break

    if not examples:
        return ""

    return (
        "\nHere are real commands already used in this codebase, for reference "
        "on syntax style (do NOT copy these unless the user's description "
        "clearly matches one):\n" + "\n".join(examples) + "\n"
    )


def _call_groq(system_prompt, user_text):
    """Low-level Groq chat call shared by extraction and explain modes.
    Returns the raw text content on success, or None on any failure."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[!] GROQ_API_KEY environment variable not set.")
        return None

    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0,
    }

    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = "(no response body)"
        print(f"[!] Groq API returned HTTP {e.code}:")
        print(f"    {body}")
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[!] Could not reach Groq API: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"[!] Could not parse AI response: {e}")
        return None


def call_groq_extract(user_text):
    """Call the Groq API to extract structured fields from free text.
    Returns a dict on success, or None on any failure (missing key,
    network error, bad JSON, etc.) so the caller can fall back gracefully.
    """
    prompt = EXTRACTION_SYSTEM_PROMPT + get_grounding_examples()
    content = _call_groq(prompt, user_text)
    if content is None:
        return None

    # Defensive: strip accidental markdown code fences
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"[!] Could not parse AI response as JSON: {e}")
        return None

    # Guarantee a summary even if the model skipped/blanked it despite
    # instructions - never leave the user with an empty summary field.
    if not (result.get("summary") or "").strip():
        result["summary"] = build_fallback_summary(result)
    return result


def build_fallback_summary(fields: dict) -> str:
    """Deterministically build a one-sentence summary from extracted
    fields, used only if the AI didn't return one."""
    command = fields.get("command") or "the configured command"

    if fields.get("validate_func"):
        validation = f"validates that {fields['validate_func']}"
    elif fields.get("expected_output"):
        validation = f"checks the output contains {fields['expected_output']!r}"
    else:
        validation = "checks that the command returns output"

    return f"Runs {command} and {validation}."


EXPLAIN_SYSTEM_PROMPT = """You explain what a gateway diagnostic test does, in
plain English, for someone reading a test framework for the first time.
Given a test's name, command, description, timeout, and validation logic,
write 2-4 sentences covering: what the command does, what specifically is
being checked (the validation logic), and why this test would matter for
a Livebox/gateway diagnostic framework. Be concrete about the actual command
and check - do not write generic filler. No markdown, plain prose only."""


def explain_testcase(testcase):
    """Reverse mode: given an existing TestCase object, ask the AI to
    explain what it does in plain English. Returns a string, or None on
    failure (missing key, network error, etc.)."""
    validation = "none (any non-empty output passes)"
    if testcase.validate_func:
        validation = "custom validator function"
    elif testcase.expected_output:
        validation = f'checks output contains "{testcase.expected_output}"'

    description = (
        f"Test name: {testcase.name}\n"
        f"Command: {testcase.command}\n"
        f"Description: {testcase.description}\n"
        f"Timeout: {testcase.timeout}s\n"
        f"Validation: {validation}"
    )
    return _call_groq(EXPLAIN_SYSTEM_PROMPT, description)


def ask_with_default(prompt, default):
    """Show an AI-extracted value as the default; Enter accepts it,
    typing anything overrides it."""
    shown = default if default not in (None, "") else None
    suffix = f" [{shown}]" if shown is not None else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val if val else (str(shown) if shown is not None else "")


def collect_testcase_ai():
    """
    AI-assisted equivalent of collect_testcase():
    asks for one free-text description, extracts fields via Groq,
    then walks the user through confirming/overriding each one.
    """

    print("\nDescribe the test in plain English. Include the exact command")
    print("if you know it, e.g.:")
    print('  Check that pcb_cli "NMC.getWanModeList()" output has both DHCP and PPPoE')

    user_text = input("\nDescribe your test: ").strip()

    if not user_text:
        print("[!] Empty description - switching to manual entry.")
        return collect_testcase()

    print("[*] Asking the AI to extract test fields...")

    extracted = call_groq_extract(user_text)
    if extracted is None:
        print("[*] Falling back to manual entry.")
        return collect_testcase()

    print("\n[*] AI-extracted fields - press Enter to accept, or type to override:")

    # Name
    while True:
        raw_name = ask_with_default(
            "Test name (snake_case)",
            extracted.get("name")
        )

        if not raw_name:
            print("[!] Test name cannot be empty.")
            continue

        name = to_snake_case(raw_name)

        if not name:
            print("[!] Invalid test name.")
            continue

        break


    # Command
    while True:
        command = ask_with_default(
            "Shell command",
            extracted.get("command")
        )

        if not command:
            print("[!] Command cannot be empty.")
            continue

        break


    # Description
    description = ask_with_default(
        "Description",
        extracted.get("description") or f"Run {name}"
    )


    # Summary
    summary = ask_with_default(
        "Summary",
        extracted.get("summary") or f"Verify {name} behavior"
    )


    # Timeout
    while True:

        raw_timeout = ask_with_default(
            "Timeout in seconds",
            extracted.get("timeout") or 5
        )

        try:
            timeout = int(raw_timeout)

            if timeout <= 0:
                print("[!] Timeout must be positive.")
                continue

            break

        except ValueError:
            print("[!] Timeout must be a number.")


    # Validation
    ai_validate_func = extracted.get("validate_func") or None

    ai_expected_output = (
        None if ai_validate_func
        else extracted.get("expected_output")
    )


    validate_func = None
    expected_output = None


    if ai_validate_func:

        validate_func = ask_with_default(
            "Validator expression (on variable o)",
            ai_validate_func
        )


    elif ai_expected_output:

        expected_output = ask_with_default(
            "Expected output substring",
            ai_expected_output
        )


    else:

        expected_output = input(
            "Expected output substring "
            "(blank = any output passes): "
        ).strip() or None


        if expected_output is None:

            validate_func = input(
                "Custom validator expression on variable o "
                "(blank = skip): "
            ).strip() or None



    return {
        "name": name,
        "summary": summary,
        "command": command,
        "description": description,
        "timeout": timeout,
        "expected_output": expected_output,
        "validate_func": validate_func,
    }



def run_add_test_ai_flow():
    """
    Entry point for python3 main.py --add-test-ai.
    """

    print("\n" + "=" * 60)
    print("ADD TEST - AI-Assisted (natural language)")
    print("=" * 60)

    testcase = collect_testcase_ai()

    suite = collect_testsuite(testcase)

    registration_key = collect_registration(suite)

    code = generate_code(
        testcase,
        suite,
        registration_key
    )

    from datetime import datetime

    print("\n" + "=" * 60)
    print("PREVIEW")
    print("=" * 60)

    print(f"Test: {testcase['name']}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # AI-generated summary of what the test does
    print("\nSummary:")
    print(testcase.get("summary") or "No summary generated.")

    # Which file this write touches, and how
    print(f"\nFile change: {CUSTOM_TESTS_FILE}")
    print(f'  → Registers a new TestCase/TestSuite as TEST_SUITES["{registration_key}"]')
    print("    (additive only - no existing tests are modified).")

    # Fields the AI pulled out of the free-text description
    print("\nExtracted:")
    print(f"  • Command:         {testcase['command']}")
    print(f"  • Timeout:         {testcase['timeout']}s")
    if testcase.get("validate_func"):
        print(f"  • Validation:      custom validator -> {testcase['validate_func']}")
    elif testcase.get("expected_output"):
        print(f"  • Validation:      expected output contains {testcase['expected_output']!r}")
    else:
        print("  • Validation:      none (any non-empty output passes)")

    print("\nGenerated code:")
    print("=" * 60)
    print(code)
    print("=" * 60)

    confirm = input(
        "Write this to custom_tests.py? [Y/n]: "
    ).strip().lower()

    if confirm not in ("", "y", "yes"):
        print("[*] Cancelled - nothing written.")
        return

    if append_to_file(code):
        print(
            f"[+] Test '{testcase['name']}' added and registered "
            f'as "{registration_key}".'
        )
    else:
        print(
            "[!] Test was not saved cleanly. Check custom_tests.py."
        )



if __name__ == "__main__":
    run_add_test_ai_flow()