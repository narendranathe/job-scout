#!/usr/bin/env python3
"""
Resume Vault CLI — Import, compare, and manage your resume collection.

Usage:
    # Bulk import from your Resume Easy folder
    python vault_cli.py import "C:\\Users\\naren\\OneDrive\\Desktop\\Resume Easy"

    # Import specific extensions only
    python vault_cli.py import "C:\\Users\\naren\\OneDrive\\Desktop\\Resume Easy" --ext .pdf

    # List all imported resumes
    python vault_cli.py list

    # Compare two versions
    python vault_cli.py compare gs_data meta_ml

    # Find best resume for a job description
    python vault_cli.py best-match "Senior Data Engineer with Spark and Kafka experience..."

    # Check resume vs job description fit
    python vault_cli.py job-fit gs_data "We need a data engineer with Python and SQL..."

    # Show vault stats
    python vault_cli.py stats

    # Parse a filename to see how it's interpreted
    python vault_cli.py parse "Narendranath_GS_data.pdf"
"""

import argparse
import json
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.db import init_db, DB_PATH
from storage.resume_vault import (
    bulk_import,
    compare_resumes,
    compare_resume_to_job,
    find_best_resume_for_job,
    list_vault,
    parse_resume_filename,
    vault_stats,
    VAULT_DIR,
)


def cmd_import(args):
    """Import resumes from a directory."""
    init_db()
    extensions = tuple(args.ext) if args.ext else (".pdf", ".docx")
    print(f"\n📂 Importing from: {args.source_dir}")
    print(f"   Extensions: {extensions}")
    print(f"   Vault: {VAULT_DIR}")
    print(f"   Database: {DB_PATH}\n")

    result = bulk_import(
        source_dir=args.source_dir,
        db_path=DB_PATH,
        extensions=extensions,
    )

    if result.get("error"):
        print(f"❌ {result['error']}")
        return

    print(f"✅ Imported: {result['imported']}")
    print(f"⏭️  Skipped:  {result['skipped']}")
    print(f"❌ Errors:   {result['errors']}")

    if result.get("files"):
        print(f"\n{'Company':<25} {'Role':<20} {'Skills':<8} {'Chars':<8} {'Key'}")
        print("─" * 90)
        for f in result["files"]:
            print(f"{f['company']:<25} {(f.get('role') or '—'):<20} {f['skills_found']:<8} {f['chars']:<8} {f['version_key']}")


def cmd_list(args):
    """List all vault files."""
    files = list_vault()
    if not files:
        print("📭 Vault is empty. Run: python vault_cli.py import <directory>")
        return

    print(f"\n📁 Resume Vault — {len(files)} files\n")
    print(f"{'Filename':<45} {'Company':<22} {'Role':<18} {'Size':<8}")
    print("─" * 95)
    for f in files:
        print(f"{f['original_filename']:<45} {f['company']:<22} {(f.get('role') or '—'):<18} {f['size_kb']}KB")


def cmd_compare(args):
    """Compare two resume versions."""
    init_db()
    result = compare_resumes(args.version_a, args.version_b, db_path=DB_PATH)

    if result.get("error"):
        print(f"❌ {result['error']}")
        return

    va = result["version_a"]
    vb = result["version_b"]

    print(f"\n🔍 Resume Comparison")
    print(f"{'─' * 60}")
    print(f"  A: {va['display']} ({va['word_count']} words, {len(va['skills'])} skills)")
    print(f"  B: {vb['display']} ({vb['word_count']} words, {len(vb['skills'])} skills)")
    print(f"{'─' * 60}")
    print(f"  📊 Similarity: {result['similarity_pct']}%")
    print(f"  💬 {result['interpretation']}")
    print(f"\n  🔗 Shared skills ({len(result['shared_skills'])}): {', '.join(result['shared_skills'])}")
    print(f"  🅰️  Only in A ({len(result['only_a'])}): {', '.join(result['only_a']) or '—'}")
    print(f"  🅱️  Only in B ({len(result['only_b'])}): {', '.join(result['only_b']) or '—'}")

    if result.get("top_differences"):
        print(f"\n  📈 Top differentiating terms:")
        for d in result["top_differences"][:10]:
            arrow = "→A" if d["delta"] > 0 else "→B"
            print(f"     {d['term']:<20} {arrow} (Δ{abs(d['delta']):.3f})")


def cmd_job_fit(args):
    """Check resume vs job description fit."""
    init_db()
    result = compare_resume_to_job(args.version_key, args.job_description, db_path=DB_PATH)

    if result.get("error"):
        print(f"❌ {result['error']}")
        return

    print(f"\n🎯 Job Fit Analysis — {args.version_key}")
    print(f"{'─' * 60}")
    print(f"  📊 TF-IDF Similarity: {result['tfidf_similarity']:.1%}")
    print(f"  🛠️  Skill Match: {result['skill_match_pct']}%")
    print(f"  💬 {result['fit']}")
    print(f"\n  ✅ Matched: {', '.join(result['matched_skills']) or '—'}")
    print(f"  ❌ Missing: {', '.join(result['missing_skills']) or '—'}")
    print(f"  ➕ Extra:   {', '.join(result['extra_skills'][:10]) or '—'}")
    print(f"\n  💡 {result['recommendation']}")


def cmd_best_match(args):
    """Rank all resumes against a job description."""
    init_db()
    results = find_best_resume_for_job(args.job_description, db_path=DB_PATH)

    if not results:
        print("📭 No resume versions found. Import some first.")
        return

    print(f"\n🏆 Best Resume Match — top {min(len(results), 10)} of {len(results)}\n")
    print(f"{'#':<4} {'Version':<30} {'Combined':<10} {'Skills':<10} {'TF-IDF':<10} {'Missing'}")
    print("─" * 100)
    for i, r in enumerate(results[:10], 1):
        missing = ", ".join(r["missing_skills"][:3])
        if len(r["missing_skills"]) > 3:
            missing += f" +{len(r['missing_skills']) - 3}"
        print(f"{i:<4} {r['display_name']:<30} {r['combined_score']:.3f}     {r['skill_match_pct']}%       {r['tfidf_similarity']:.3f}     {missing or '—'}")


def cmd_stats(args):
    """Show vault statistics."""
    init_db()
    s = vault_stats(db_path=DB_PATH)
    print(f"\n📊 Resume Vault Stats")
    print(f"{'─' * 40}")
    print(f"  📁 Vault path:      {s['vault_path']}")
    print(f"  📄 PDF files:       {s['pdf_count']}")
    print(f"  📝 Text extracts:   {s['text_count']}")
    print(f"  💾 Total size:      {s['total_size_mb']} MB")
    print(f"  🏢 Companies:       {s['unique_companies']}")
    print(f"  🗄️  DB versions:     {s['db_versions']}")
    if s.get("companies"):
        print(f"\n  Companies: {', '.join(s['companies'][:20])}")
        if len(s['companies']) > 20:
            print(f"             ... and {len(s['companies']) - 20} more")


def cmd_parse(args):
    """Parse a filename to show interpretation."""
    result = parse_resume_filename(args.filename)
    print(f"\n📋 Filename Parser")
    print(f"{'─' * 40}")
    for k, v in result.items():
        print(f"  {k:<20} {v}")


def main():
    parser = argparse.ArgumentParser(
        description="Resume Vault CLI — manage your resume collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # import
    p_import = sub.add_parser("import", help="Bulk import from directory")
    p_import.add_argument("source_dir", help="Path to resume folder")
    p_import.add_argument("--ext", nargs="+", default=None, help="Extensions to import (default: .pdf .docx)")

    # list
    sub.add_parser("list", help="List vault files")

    # compare
    p_compare = sub.add_parser("compare", help="Compare two resume versions")
    p_compare.add_argument("version_a", help="First version key")
    p_compare.add_argument("version_b", help="Second version key")

    # job-fit
    p_fit = sub.add_parser("job-fit", help="Check resume vs job description")
    p_fit.add_argument("version_key", help="Resume version key")
    p_fit.add_argument("job_description", help="Job description text")

    # best-match
    p_best = sub.add_parser("best-match", help="Rank resumes against a job")
    p_best.add_argument("job_description", help="Job description text")

    # stats
    sub.add_parser("stats", help="Vault statistics")

    # parse
    p_parse = sub.add_parser("parse", help="Parse a resume filename")
    p_parse.add_argument("filename", help="Filename to parse")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    commands = {
        "import": cmd_import,
        "list": cmd_list,
        "compare": cmd_compare,
        "job-fit": cmd_job_fit,
        "best-match": cmd_best_match,
        "stats": cmd_stats,
        "parse": cmd_parse,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
