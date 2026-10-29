from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_tools.colab_runner import ensure_training_packages, execute_notebook
from ai_tools.notebook_job import notebook_job


class ColabRunnerTests(unittest.TestCase):
    def test_matching_packages_do_not_install_or_import_them_into_kernel(self):
        with patch("ai_tools.colab_runner.metadata.version", return_value="1.0"), patch("ai_tools.colab_runner.subprocess.run") as run:
            ensure_training_packages({"example": "1.0"})
            run.assert_not_called()

    def test_installation_failure_reports_original_error_instead_of_model_nameerror(self):
        with patch("ai_tools.colab_runner.metadata.version", side_effect=metadata.PackageNotFoundError), \
             patch("ai_tools.colab_runner.subprocess.run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="package download failed")):
            with self.assertRaisesRegex(RuntimeError, "package download failed"):
                ensure_training_packages({"example": "1.0"})

    def test_invalid_configuration_fails_before_installation(self):
        with patch("ai_tools.colab_runner.ensure_training_packages") as ensure:
            with self.assertRaises(ValueError):
                execute_notebook(mode="bad", cart_text="", baskets=2000, source="", requirements={})
            ensure.assert_not_called()

    def test_worker_handles_unknown_cart_without_inventing_suggestions(self):
        with TemporaryDirectory() as directory:
            result = notebook_job({"mode": "demo", "output": str(Path(directory) / "run"), "baskets": 100,
                                   "cart_text": "Món không tồn tại", "csv_path": None})
            self.assertEqual(result["suggestions"], [])
            self.assertEqual(result["unknown"], ["Món không tồn tại"])
            self.assertTrue((Path(directory) / "run/apriori_model.json").is_file())

    def test_worker_resolves_names_and_excludes_selected_dishes(self):
        with TemporaryDirectory() as directory:
            result = notebook_job({"mode": "demo", "output": str(Path(directory) / "run"), "baskets": 500,
                                   "cart_text": "Cơm trắng, Rau xào", "csv_path": None})
            self.assertEqual(set(result["cart"]), {"DEMO08", "DEMO09"})
            self.assertFalse(set(result["cart"]) & set(result["suggestions"]))
            self.assertIn("DEMO07", result["suggestions"])

    def test_worker_with_empty_cart_chooses_a_working_example(self):
        with TemporaryDirectory() as directory:
            result = notebook_job({"mode": "demo", "output": str(Path(directory) / "run"), "baskets": 500,
                                   "cart_text": "", "csv_path": None})
            self.assertTrue(result["cart"])
            self.assertTrue(result["suggestions"])
