"""
The scripts in backend/scripts/ at least parse and expose their arguments.

Nothing else imports them, so a syntax error in one survives a full green test
run and only shows up when somebody tries to spend money with it - which is
exactly how eval_ir_parser.py shipped with an unterminated f-string, after the
suite passed and the commit went out.

This is not a test of what they do. It is a test that they load, which is the
failure that actually happened.
"""
import importlib.util
import pathlib

import pytest

SCRIPTS = sorted((pathlib.Path(__file__).resolve().parents[1] / "scripts").glob("*.py"))


def test_there_are_scripts_to_check():
    """If the directory moves, this file should fail rather than quietly pass
    by checking nothing."""
    assert SCRIPTS, "no scripts found - has backend/scripts/ moved?"


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_script_parses(path):
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_script_imports_and_builds_its_arguments(path):
    """Loads the module and runs its argument parser with --help.

    Catches more than a syntax error: a script referencing a helper that has
    been renamed, or an argparse option declared twice, both of which look fine
    until the moment you want the run.

    Importing is safe because these do their work under `if __name__ ==
    "__main__"`, and --help exits before any API call.
    """
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "main"):
        return
    with pytest.raises(SystemExit) as exit_info:
        import sys
        argv = sys.argv
        sys.argv = [path.name, "--help"]
        try:
            module.main()
        finally:
            sys.argv = argv
    assert exit_info.value.code == 0
