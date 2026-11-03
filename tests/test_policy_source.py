from pathlib import Path
from unittest.mock import patch

import pytest

from emporio.cli import main
from emporio.policy import PolicySourceError
from emporio.policy_source import PdfPolicyRetriever


def test_missing_pdf_is_a_typed_source_error(tmp_path: Path) -> None:
    with pytest.raises(PolicySourceError):
        PdfPolicyRetriever.from_path(tmp_path / "missing.pdf")


def test_cli_returns_safe_response_for_missing_pdf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main(
        [
            "--policy-source",
            str(tmp_path / "missing.pdf"),
            "--query",
            "Qual o horário de funcionamento?",
        ]
    )

    output = capsys.readouterr().out
    assert result == 2
    assert "manual da loja" in output
    assert "Traceback" not in output


def test_cli_renders_successful_policy_answer(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("emporio.cli.PdfPolicyRetriever.from_path") as load_source:
        from emporio.policy_source import TextPolicyRetriever

        load_source.return_value = TextPolicyRetriever.from_text(
            "2 Hours\nSaturday from 9h to 13h."
        )
        result = main(
            [
                "--policy-source",
                "policy.pdf",
                "--query",
                "What are the Saturday hours?",
            ]
        )

    output = capsys.readouterr().out
    assert result == 0
    assert "Saturday from 9h to 13h" in output
    assert "Fonte: fixture.txt" in output


def test_cli_returns_safe_response_for_malformed_pdf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    malformed = tmp_path / "malformed.pdf"
    malformed.write_bytes(b"not a PDF")

    result = main(
        [
            "--policy-source",
            str(malformed),
            "--query",
            "What are the store hours?",
        ]
    )

    output = capsys.readouterr().out
    assert result == 2
    assert "manual da loja" in output
    assert "Traceback" not in output
