"""Command line: python -m boomi_release <command> [options]. Run with -h for details."""
import argparse
import os
import sys

from . import gh
from . import manifest as mf
from .api import BoomiClient, BoomiError

DEFAULT_MANIFEST = "release/release.json"


def main(argv=None):
    p = argparse.ArgumentParser(prog="boomi_release", description="Boomi release automation for CI/CD pipelines.")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="build the manifest from Packaged Components in a folder")
    d.add_argument("--folder", required=True, help="folder path, e.g. Integrations/Orders")
    d.add_argument("--branch", default="main", help="Boomi branch to take packages from (default: main)")
    d.add_argument("--test-suffix", default=" - Test", help='harness naming suffix (default: " - Test")')
    d.add_argument("--out", default=DEFAULT_MANIFEST)

    df = sub.add_parser("diff", help="print a Markdown summary of two manifests")
    df.add_argument("old")
    df.add_argument("new")

    li = sub.add_parser("lint", help="lint the packaged version of every component")
    li.add_argument("--manifest", default=DEFAULT_MANIFEST)
    li.add_argument("--fail-on", default="", help="comma-separated priorities that fail, e.g. MAJOR,MINOR")
    li.add_argument("--rules", default=None, help="custom rules JSON (default: built-in)")

    de = sub.add_parser("deploy", help="deploy the manifest to an environment")
    de.add_argument("--manifest", default=DEFAULT_MANIFEST)
    de.add_argument("--env", required=True, help="Boomi environment name")
    de.add_argument("--label", default=None)
    de.add_argument("--dry-run", action="store_true")

    te = sub.add_parser("test", help="run test harnesses and write JUnit files")
    te.add_argument("--manifest", default=DEFAULT_MANIFEST)
    te.add_argument("--env", required=True)
    te.add_argument("--runtime", required=True, help="Boomi runtime (Atom) name in that environment")
    te.add_argument("--out-dir", default=".")

    pr = sub.add_parser("promote", help="promote what runs in one environment to the next")
    pr.add_argument("--manifest", default=DEFAULT_MANIFEST)
    pr.add_argument("--from", dest="source", required=True)
    pr.add_argument("--to", dest="target", required=True)
    pr.add_argument("--label", required=True, help="e.g. QA or PROD (PROD requires --ticket)")
    pr.add_argument("--ticket", default="")
    pr.add_argument("--actor", default=os.environ.get("GITHUB_ACTOR", "unknown"))
    pr.add_argument("--notes-out", default="promotion-notes.md")
    pr.add_argument("--dry-run", action="store_true")

    rb = sub.add_parser("rollback", help="restore the previously deployed packages in an environment")
    rb.add_argument("--manifest", default=DEFAULT_MANIFEST)
    rb.add_argument("--env", required=True)
    rb.add_argument("--label", default=None)
    rb.add_argument("--component", default="", help="only this component name")
    rb.add_argument("--component-ids", default="", help="only these comma-separated component ids")
    rb.add_argument("--reason", default="rollback")
    rb.add_argument("--actor", default=os.environ.get("GITHUB_ACTOR", "unknown"))
    rb.add_argument("--dry-run", action="store_true")

    sa = sub.add_parser("samples", help="create the demo components in a Boomi folder")
    sa.add_argument("--folder-id", required=True)
    sa.add_argument("--package", default=None, help="also package the processes at this version, e.g. 1.0")

    args = p.parse_args(argv)

    if args.command == "diff":
        sys.stdout.write(mf.diff_markdown(mf.load(args.old), mf.load(args.new)))
        return 0

    try:
        client = BoomiClient()
        if args.command == "discover":
            from .discover import discover
            release = discover(client, args.folder, args.branch, args.test_suffix)
            mf.save(args.out, release)
            print(f"[discover] wrote {len(release['components'])} component(s) to {args.out}")
        elif args.command == "lint":
            from .lint import lint
            blocking = lint(client, mf.load(args.manifest), args.fail_on.split(","), args.rules)
            return 1 if blocking else 0
        elif args.command == "deploy":
            from .deploy import deploy_release
            deployed = deploy_release(client, mf.load(args.manifest), args.env, args.label, dry_run=args.dry_run)
            gh.output("deployed", ",".join(deployed))
        elif args.command == "test":
            from .testing import run_tests
            failed = run_tests(client, mf.load(args.manifest), args.env, args.runtime, args.out_dir)
            return 1 if failed else 0
        elif args.command == "promote":
            from .deploy import promote
            body = promote(client, mf.load(args.manifest), args.source, args.target, args.label,
                           args.ticket, args.actor, args.dry_run)
            with open(args.notes_out, "w", encoding="utf-8") as f:
                f.write(body)
        elif args.command == "rollback":
            from .deploy import rollback
            ids = {i.strip() for i in args.component_ids.split(",") if i.strip()}
            rollback(client, mf.load(args.manifest), args.env, args.label, ids, args.component,
                     args.reason, args.actor, args.dry_run)
        elif args.command == "samples":
            from .samples import create_samples
            create_samples(client, args.folder_id, args.package)
    except BoomiError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
