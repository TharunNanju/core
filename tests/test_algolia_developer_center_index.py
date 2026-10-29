#!/usr/bin/env python3
"""Regression tests for localized Software Algolia record generation."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = CORE_ROOT / "scripts" / "ci" / "sync_algolia_developer_center_index.py"
SPEC = importlib.util.spec_from_file_location("software_algolia_index", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LocalizedRecordTests(unittest.TestCase):
    def test_generates_language_specific_records_and_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs_dir = root / "docs"
            localized_dir = (
                root
                / "i18n"
                / "uk"
                / "docusaurus-plugin-content-docs"
                / "current"
            )
            (docs_dir / "getting-started").mkdir(parents=True)
            (localized_dir / "getting-started").mkdir(parents=True)
            (docs_dir / "getting-started" / "index.md").write_text(
                "# Getting started\nEnglish body.\n",
                encoding="utf-8",
            )
            (localized_dir / "getting-started" / "index.md").write_text(
                "# Початок роботи\nУкраїнський текст.\n",
                encoding="utf-8",
            )

            records, summary = MODULE.generate_records(
                docs_dir,
                "https://build.neat.sima.ai",
                MODULE.DEFAULT_MAX_RECORD_BYTES,
                root / "i18n",
            )

            self.assertEqual(summary["by_language"], {"en": 1, "uk": 1})
            by_language = {record["language"]: record for record in records}
            self.assertEqual(by_language["en"]["route"], "/software/getting-started")
            self.assertEqual(by_language["uk"]["route"], "/software/uk/getting-started")
            self.assertNotEqual(by_language["en"]["objectID"], by_language["uk"]["objectID"])

    def test_localized_record_uses_frontmatter_slug(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs_dir = root / "docs"
            localized_dir = (
                root
                / "i18n"
                / "ja"
                / "docusaurus-plugin-content-docs"
                / "current"
                / "develop-apps/tutorials/models-inference"
            )
            docs_dir.mkdir()
            localized_dir.mkdir(parents=True)
            (localized_dir / "tutorial_001_run_your_first_model.mdx").write_text(
                "---\nslug: /tutorials/run-your-first-model\n---\n\n# 最初のモデル\n本文。\n",
                encoding="utf-8",
            )

            records, _ = MODULE.generate_records(
                docs_dir,
                "https://developer.sima.ai",
                MODULE.DEFAULT_MAX_RECORD_BYTES,
                root / "i18n",
            )

            self.assertEqual(len(records), 1)
            self.assertEqual(
                records[0]["url"],
                "https://developer.sima.ai/software/ja/tutorials/run-your-first-model",
            )
            self.assertEqual(
                records[0]["route"],
                "/software/ja/tutorials/run-your-first-model",
            )

    def test_localized_record_uses_frontmatter_title_without_h1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs_dir = root / "docs"
            (docs_dir / "reference").mkdir(parents=True)
            (docs_dir / "reference" / "env_vars.md").write_text(
                "---\ntitle: Environment variables\n---\n\nEnglish body.\n",
                encoding="utf-8",
            )
            titles = {
                "ko": "환경 변수",
                "ja": "環境変数",
                "zh-Hant": "環境變數",
                "uk": "Змінні середовища",
            }
            for locale, title in titles.items():
                localized_dir = root / "i18n" / locale / MODULE.I18N_DOCS_SUBDIR / "reference"
                localized_dir.mkdir(parents=True)
                (localized_dir / "env_vars.md").write_text(
                    f'---\ntitle: "{title}"\n---\n\nLocalized body.\n',
                    encoding="utf-8",
                )

            records, _ = MODULE.generate_records(
                docs_dir,
                "https://developer.sima.ai",
                MODULE.DEFAULT_MAX_RECORD_BYTES,
                root / "i18n",
            )

            by_language = {record["language"]: record for record in records}
            self.assertEqual(by_language["en"]["title"], "Environment variables")
            for locale, title in titles.items():
                self.assertEqual(by_language[locale]["title"], title)
                self.assertEqual(by_language[locale]["hierarchy"]["lvl1"], title)

    def test_title_prefers_h1_then_frontmatter_then_filename(self) -> None:
        path = Path("data_formats.md")
        self.assertEqual(
            MODULE.title_from_markdown(path, "# Data formats and tensors\nBody.\n", "Tensor formats"),
            "Data formats and tensors",
        )
        self.assertEqual(
            MODULE.title_from_markdown(path, "Body.\n", "`Tensor` formats"),
            "Tensor formats",
        )
        self.assertEqual(MODULE.title_from_markdown(path, "Body.\n"), "Data Formats")
        self.assertEqual(MODULE.title_from_markdown(Path("env-vars.md"), "Body.\n", ""), "Env Vars")


class ReleaseRecordTests(unittest.TestCase):
    def test_resolves_versions_in_all_locales_before_parsing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            roots = [docs] + [root / "i18n" / locale / MODULE.I18N_DOCS_SUBDIR for locale in ["ko", "ja", "zh-Hant", "uk"]]
            source = (
                "---\nslug: /sdk-%%release.sdk%%\n---\n"
                "# Neat SDK %%release.sdk%%\n"
                "Install `sdk@%%release.sdk_channel%%`; series %%release.sdk_series%%. "
                "Core %%release.core%%; compiler %%release.model_compiler%%. Minimum SDK 2.1.3.0.\n"
            )
            for doc_root in roots:
                doc_root.mkdir(parents=True)
                (doc_root / "index.md").write_text(source, encoding="utf-8")
            records, _ = MODULE.generate_records(docs, "https://developer.sima.ai", MODULE.DEFAULT_MAX_RECORD_BYTES, root / "i18n")
            snapshot = json.loads((CORE_ROOT / "website/release-data/current.json").read_text())
            values = {key: item["value"] for key, item in snapshot["releases"].items()}
            self.assertEqual({record["language"] for record in records}, {"en", "ko", "ja", "zh-Hant", "uk"})
            for record in records:
                self.assertNotIn("%release", json.dumps(record))
                self.assertEqual(record["title"], f"Neat SDK {values['sdk']}")
                self.assertIn(f"sdk@{values['sdk_channel']}", record["content"])
                self.assertIn(f"series {values['sdk_series']}", record["content"])
                self.assertIn(f"Core {values['core']}", record["content"])
                self.assertIn("Minimum SDK 2.1.3.0", record["content"])
                self.assertTrue(record["url"].endswith(f"/sdk-{values['sdk']}"))
            self.assertEqual((docs / "index.md").read_text(encoding="utf-8"), source)

    def test_invalid_tokens_fail_before_fenced_content_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory)
            page = docs / "index.md"
            for token in ("%%release.missing%%", "%%release.sdk%"):
                with self.subTest(token=token):
                    page.write_text(f"# SDK\nVisible prose.\n```bash\n{token}\n```\n", encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, r"index.md:4:.*release"):
                        MODULE.generate_records(docs, "https://developer.sima.ai", MODULE.DEFAULT_MAX_RECORD_BYTES)


if __name__ == "__main__":
    unittest.main()
