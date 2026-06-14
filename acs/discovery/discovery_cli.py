"""Discovery CLI — command-line entry point for source discovery.

Usage:
  python -m acs.discovery.discovery_cli --topic "..." --keywords "a,b" --provider mock
  python -m acs.discovery.discovery_cli --topic "..." --provider import-file --input data.csv
  python -m acs.discovery.discovery_cli --provider sitemap --sitemap-url https://x.com/sitemap.xml
  python -m acs.discovery.discovery_cli --provider rss --feed-url https://x.com/feed.xml
"""
import argparse
import json
import sys

from .source_discovery import SourceDiscovery


def main():
    p = argparse.ArgumentParser(description="ACS Source Discovery CLI")
    p.add_argument("--topic", default="", help="Search topic")
    p.add_argument("--keywords", default="", help="Comma-separated keywords")
    p.add_argument("--provider", default="mock",
                   choices=["mock", "import-file", "sitemap", "rss"],
                   help="Discovery provider")
    p.add_argument("--input", default="", help="Input file (for import-file provider)")
    p.add_argument("--sitemap-url", default="", help="Sitemap URL (for sitemap provider)")
    p.add_argument("--feed-url", default="", help="RSS/Atom feed URL (for rss provider)")
    p.add_argument("--limit", type=int, default=50, help="Max results")
    p.add_argument("--auto-select", action="store_true", help="Auto-select allowed candidates")
    p.add_argument("--output", default="", help="Output JSON path")
    p.add_argument("--list-providers", action="store_true", help="List registered providers")
    args = p.parse_args()

    if args.list_providers:
        from .provider_registry import get_registry
        reg = get_registry()
        for p_info in reg.list_providers():
            print(f"  {p_info['name']:16s} {p_info['description']}")
        sys.exit(0)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
    sd = SourceDiscovery()

    result = sd.discover(
        topic=args.topic,
        keywords=keywords,
        provider=args.provider,
        limit=args.limit,
        auto_select_allowed=args.auto_select,
        extra_params={
            "input_path": args.input,
            "sitemap_url": args.sitemap_url,
            "feed_url": args.feed_url,
        },
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved to {args.output}")

    print(json.dumps(result["report"], ensure_ascii=False, indent=2))
    print(f"\nCandidates: {len(result['candidates'])}")
    print(f"Selected URLs: {result['selected_urls_path']}")


if __name__ == "__main__":
    main()
