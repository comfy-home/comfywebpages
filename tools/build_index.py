#!/usr/bin/env python3
"""Rebuild packs/ + index.json from src/ submissions.

Port of comfyweb's `repo_tree::generate_index` — keep behavior in sync with
apps/modules/comfyweb/src/cw_pages/repo_tree.rs.

Layout:
    src/<host>/<YYYY-MM-DD>_<ord>_<uid>/manifest.json   # pack metadata
    src/<host>/<YYYY-MM-DD>_<ord>_<uid>/config.json    # {"rules": [...]} or bare array
    packs/<host>/<subdir>.json                          # generated CwpPack
    index.json                                          # generated CwpIndex catalog

Submissions whose manifest names a `supersedes` folder drop the superseded
submission from the index but still write its pack (history stays fetchable).
`src/_profiles/…` submissions index as kind="profile" presets.
"""

import json
import sys
from pathlib import Path

PROFILES_DIR = "_profiles"

INDEX_METADATA = {
    "name": "ComfyWebPages Community",
    "author": "",
    "description": "Community-curated ComfyWebPages rulesets",
}

MANIFEST_FIELDS = (
    "name",
    "author",
    "email",
    "description",
    "version",
    "license",
    "supersedes",
    "homepage",
)


def fail(msg: str) -> "None":
    print(f"build_index: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_config(path: Path, ctx: str) -> list:
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        fail(f"{ctx}/config.json: {e}")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("rules"), list):
        return data["rules"]
    fail(f"{ctx}/config.json: expected a rules array or {{\"rules\": [...]}}")


def scan(repo_root: Path) -> list:
    """Return submissions as dicts {id, host_dir, subdir, manifest, rules}."""
    src = repo_root / "src"
    out = []
    if not src.is_dir():
        return out
    for host_path in sorted(p for p in src.iterdir() if p.is_dir()):
        host_dir = host_path.name
        subs = sorted(
            p
            for p in host_path.iterdir()
            if p.is_dir()
            and (p / "manifest.json").is_file()
            and (p / "config.json").is_file()
        )
        for sub_path in subs:
            subdir = sub_path.name
            ctx = f"{host_dir}/{subdir}"
            try:
                raw = json.loads((sub_path / "manifest.json").read_text())
            except Exception as e:
                fail(f"{ctx}/manifest.json: {e}")
            if not isinstance(raw, dict):
                fail(f"{ctx}/manifest.json: expected an object")
            manifest = {k: raw.get(k, "") for k in MANIFEST_FIELDS}
            rules = parse_config(sub_path / "config.json", ctx)
            out.append(
                {
                    "id": ctx,
                    "host_dir": host_dir,
                    "subdir": subdir,
                    "manifest": manifest,
                    "rules": rules,
                }
            )
    return out


def submission_to_pack(sub: dict) -> dict:
    created = sub["subdir"].split("_")[0]
    m = sub["manifest"]
    return {
        "schema_version": 1,
        "metadata": {
            "pack_id": sub["id"],
            "name": m["name"] or sub["id"],
            "author": m["author"],
            "version": m["version"],
            "created_at": created,
            "license": m["license"],
            "source_url": m["homepage"],
        },
        "rules": sub["rules"],
    }


def generate(repo_root: Path) -> int:
    subs = scan(repo_root)
    superseded = {
        f"{s['host_dir']}/{s['manifest']['supersedes']}"
        for s in subs
        if s["manifest"]["supersedes"]
    }

    entries = []
    for sub in subs:
        pack = submission_to_pack(sub)
        rel = f"packs/{sub['host_dir']}/{sub['subdir']}.json"
        out_path = repo_root / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n")
        if sub["id"] in superseded:
            continue
        entries.append(
            {
                "id": sub["id"],
                "name": pack["metadata"]["name"],
                "author": pack["metadata"]["author"],
                "description": sub["manifest"]["description"],
                "version": pack["metadata"]["version"],
                "url": rel,
                "updated_at": sub["subdir"].split("_")[0],
                "kind": "profile" if sub["host_dir"] == PROFILES_DIR else "",
            }
        )

    index = {"schema_version": 1, "metadata": INDEX_METADATA, "packs": entries}
    (repo_root / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    )
    return len(entries)


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    count = generate(root)
    print(f"build_index: {count} pack(s) indexed")
