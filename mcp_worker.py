"""One-shot bridge between MCP tools and the unchanged MOFh6 query system."""

import json
import re
import sys
import time
import traceback
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "request"))


def _system():
    from request.config.config import load_config
    from request.core.query_system import ChemicalQuerySystem

    config = load_config(str(PROJECT_DIR / "extrfinetune" / "config.json"))
    return ChemicalQuerySystem(config)


def _run(operation: str, value: str) -> dict:
    value = value.strip()

    if operation == "download":
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Provide a CCDC code, for example ABAYUY.")
        code = value.upper()
        input_dir = PROJECT_DIR / "ulanggraph" / "input"
        before = {str(path): path.stat().st_mtime_ns for path in input_dir.glob(f"{code}.*")}
        system = _system()
        answer = system.get_synthesis_info(code)
        if answer.lstrip().startswith("❌"):
            raise RuntimeError(answer.strip())
        text_file = input_dir / f"{code}.txt"
        if not text_file.is_file():
            raise RuntimeError(
                f"Crawler did not create {text_file}. "
                "Check the publisher downloader, network access, and its credentials."
            )
        files = sorted(
            str(path.resolve())
            for path in input_dir.glob(f"{code}.*")
            if path.is_file() and path.stat().st_mtime_ns != before.get(str(path))
        )
        return {"ccdc_code": code, "message": answer.strip(), "new_or_modified_files": files}

    if operation == "process_pdf":
        pdf = Path(value).expanduser().resolve()
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            raise ValueError(f"PDF file not found: {pdf}")
        system = _system()
        result = system.process_pdf(str(pdf))
        if result is None:
            raise RuntimeError(f"PDF processing failed: {pdf}")
        text_path = PROJECT_DIR / "ulanggraph" / "input" / f"{pdf.stem}.txt"
        return {
            "pdf_path": str(pdf),
            "text_path": str(text_path.resolve()),
            "filename": result["filename"],
        }

    if operation == "workflow":
        target = value
        if value.lower().endswith(".pdf"):
            pdf = Path(value).expanduser().resolve()
            if not pdf.is_file():
                raise ValueError(f"PDF file not found: {pdf}")
            system = _system()
            if system.process_pdf(str(pdf)) is None:
                raise RuntimeError(f"PDF processing failed: {pdf}")
            target = str(pdf)
        elif not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Provide a CCDC code or an absolute PDF path.")
        else:
            system = _system()
        started_ns = time.time_ns()
        answer = system.trigger_workflow(target)
        if answer and answer.lstrip().startswith(("❌", "⚠️")):
            raise RuntimeError(answer.strip())
        output_dir = PROJECT_DIR / "ulanggraph" / "output" / "final"
        files = sorted(
            str(path.resolve()) for path in output_dir.rglob("*")
            if path.is_file() and path.stat().st_mtime_ns >= started_ns
        )
        return {
            "target": target,
            "message": answer.strip() or "Workflow completed.",
            "new_or_modified_files": files,
        }

    if operation == "ask":
        system = _system()
        answer = system.get_answer(value)
        if answer and ("Literature retrieval completed" in answer or "文献获取已完成" in answer):
            code = system.active_rag_context
            if code and not (PROJECT_DIR / "ulanggraph" / "input" / f"{code}.txt").is_file():
                raise RuntimeError(
                    f"Literature retrieval reported completion, but {code}.txt was not created. "
                    "Check the publisher downloader, network access, and its credentials."
                )
        return {"question": value, "answer": str(answer or "").strip()}

    raise ValueError(f"Unknown operation: {operation}")


def main() -> int:
    result_path = Path(sys.argv[1])
    try:
        request = json.load(sys.stdin)
        data = _run(request["operation"], request["value"])
        result = {"ok": True, "data": data}
        exit_code = 0
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        result = {"ok": False, "error": str(exc)}
        exit_code = 1
    result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
