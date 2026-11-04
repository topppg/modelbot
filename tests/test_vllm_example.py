import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "modelbot-validate"


@unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "requires Bash and jq")
class VllmExampleTests(unittest.TestCase):
    def test_generation_result_and_server_cleanup(self):
        for response, expected in [("Paris", 0), ("   ", 1)]:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                programs = {
                    "vllm": """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FIXTURE/args"
echo "$$" > "$FIXTURE/pid"
exec sleep 60
""",
                    "curl": """#!/usr/bin/env bash
case "${@: -1}" in
  */v1/models)
    test -s "$FIXTURE/pid" || exit 1
    jq -nc --arg id "$(tail -1 "$FIXTURE/args")" '{data:[{id:$id}]}'
    ;;
  */v1/completions)
    jq -nc --arg text "$RESPONSE" '{choices:[{text:$text}]}'
    ;;
  *) exit 1 ;;
esac
""",
                }
                for name, program in programs.items():
                    executable = folder / name
                    executable.write_text(program)
                    executable.chmod(0o755)
                revision = "a" * 40
                result = subprocess.run(
                    ["bash", str(SCRIPT)],
                    env={
                        **os.environ,
                        "PATH": f"{folder}:{os.environ['PATH']}",
                        "MODELBOT_MODEL": "org/model",
                        "MODELBOT_REVISION": revision,
                        "MODELBOT_STARTUP_SECONDS": "5",
                        "FIXTURE": directory,
                        "RESPONSE": response,
                    },
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                args = (folder / "args").read_text().splitlines()
                self.assertEqual(args[:2], ["serve", "org/model"])
                for flag in ("--revision", "--tokenizer-revision"):
                    self.assertEqual(args[args.index(flag) + 1], revision)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int((folder / "pid").read_text()), 0)
