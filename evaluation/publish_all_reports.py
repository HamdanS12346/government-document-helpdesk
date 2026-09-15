# Publish all evaluation reports in the evaluation/reports directory to Langfuse.
#
# Usage:
#     python -m evaluation.publish_all_reports
#
# This script can be run after any evaluation runners have generated their JSON
# report files. It will read all *.json files in the evaluation/reports folder
# and publish them using LangfuseReporter.publish_directory.

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.langfuse_reporting import LangfuseReporter


def main() -> int:
    reports_dir = PROJECT_ROOT / "evaluation" / "reports"
    if not reports_dir.is_dir():
        print(f"Reports directory not found: {reports_dir}", file=sys.stderr)
        return 1

    try:
        reporter = LangfuseReporter.from_environment()
    except Exception as e:
        print(f"Failed to initialize LangfuseReporter: {e}", file=sys.stderr)
        return 1

    published = reporter.publish_directory(reports_dir)
    print(f"Published {len(published)} report(s) to Langfuse: {', '.join(published)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
