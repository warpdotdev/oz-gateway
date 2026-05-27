import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_public_readiness",
        ROOT / "scripts" / "audit_public_readiness.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicSampleTests(unittest.TestCase):
    def test_public_sample_files_pass_placeholder_audit(self):
        audit = load_audit_module()

        findings = audit.scan_paths(audit.paths_for_scope("samples"))

        self.assertEqual([], findings, [finding.format() for finding in findings])

    def test_audit_detects_secret_like_literals_and_custom_terms(self):
        audit = load_audit_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sample = temp_path / "sample.txt"
            sample.write_text(
                "\n".join(
                    [
                        "API_TOKEN=real-secret-value",
                        "This line mentions InternalCodename.",
                    ]
                ),
                encoding="utf-8",
            )
            terms_file = temp_path / "denylist.txt"
            terms_file.write_text("InternalCodename\n", encoding="utf-8")

            findings = audit.scan_paths([sample], audit.load_terms(terms_file))

        rules = {finding.rule for finding in findings}
        self.assertIn("credential-literal", rules)
        self.assertIn("proprietary-term", rules)


if __name__ == "__main__":
    unittest.main()
