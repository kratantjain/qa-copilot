"""Command-line interface:  qa-copilot analyze|generate|run|ui ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Settings
from .engine import DEFAULT_SPEC, DOMAINS, analyze, generate
from .exporters import EXPORTERS, export
from .log import setup as setup_logging
from .providers import PROVIDERS, LLMError, get_provider


def _read_story(args) -> str:
    if args.story_file:
        return Path(args.story_file).read_text(encoding="utf-8")
    if args.story:
        return args.story
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide a requirement via --story, --story-file or stdin.")


def _parse_spec(text: str | None) -> dict[str, int]:
    if not text:
        return dict(DEFAULT_SPEC)
    spec = {}
    for part in text.split(","):
        name, _, n = part.partition("=")
        spec[name.strip()] = int(n or 2)
    return spec


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qa-copilot", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, spec=False):
        sp.add_argument("--story", help="requirement text")
        sp.add_argument("--story-file", help="read requirement from file")
        sp.add_argument("--domain", default="General", choices=DOMAINS)
        sp.add_argument("--provider", choices=PROVIDERS)
        sp.add_argument("--model")
        sp.add_argument("--out", default="out", help="output directory")
        sp.add_argument("--format", default="md", help=f"comma list of: {', '.join(EXPORTERS)}")
        if spec:
            sp.add_argument("--spec", help="e.g. Positive=4,Negative=3,Security=2")

    common(sub.add_parser("analyze", help="requirement analysis only"))
    common(sub.add_parser("generate", help="test cases only"), spec=True)
    common(sub.add_parser("run", help="analysis + test cases + exports"), spec=True)
    ui = sub.add_parser("ui", help="launch the web UI")
    ui.add_argument("--port", type=int, default=8080)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()
    if args.cmd == "ui":
        from .ui.app import run
        run(port=args.port)
        return 0

    s = Settings()
    if args.provider:
        s.provider = args.provider
    if args.model:
        s.model = args.model
    provider = get_provider(s)
    story = _read_story(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        analysis = suite = None
        if args.cmd in ("analyze", "run"):
            print(f"[1/2] Analysing with {provider.name}:{provider.model} ...", file=sys.stderr)
            analysis = analyze(provider, story, args.domain)
            print(f"Readiness: {analysis.readiness_score}/100 - {analysis.readiness_verdict}")
        if args.cmd in ("generate", "run"):
            suite = generate(provider, story, analysis, args.domain, _parse_spec(args.spec),
                             progress=lambda m: print(m, file=sys.stderr))
            print(f"Generated {len(suite.test_cases)} test cases")
    except (LLMError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    from .models import Suite
    suite_or_empty = suite or Suite(story=story)
    for fmt in [f.strip() for f in args.format.split(",") if f.strip()]:
        data, ext = export(fmt, suite_or_empty, analysis)
        path = out / f"qa_{fmt}.{ext}" if fmt in ("csv", "jira") else out / f"qa_report.{ext}"
        path.write_bytes(data)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
