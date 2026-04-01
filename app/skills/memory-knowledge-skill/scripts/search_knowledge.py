#!/usr/bin/env python3
"""
Search the knowledge base.

Usage:
    python search_knowledge.py <keyword> [options]

Options:
    --type, -t      Search type: experience, principles, or all (default: all)
    --tag, -T       Filter by tag

Examples:
    python search_knowledge.py "database" --type experience
    python search_knowledge.py "async" --tag performance
    python search_knowledge.py "security" --type principles
"""

import argparse
import re
from pathlib import Path


def search_files(base_path: Path, keyword: str, search_type: str, tag: str = None):
    """Search knowledge base files."""
    results = []
    
    # Determine search directories
    if search_type == "experience":
        dirs = [base_path / "base" / "experience"]
    elif search_type == "principles":
        dirs = [base_path / "base" / "principles"]
    else:
        dirs = [base_path / "base" / "experience", base_path / "base" / "principles"]
    
    for dir_path in dirs:
        if not dir_path.exists():
            continue
        
        for md_file in dir_path.glob("*.md"):
            if md_file.name == "INDEX.md":
                continue
            
            content = md_file.read_text(encoding='utf-8')
            
            # Keyword match
            keyword_match = not keyword or keyword.lower() in content.lower()
            
            # Tag match
            tag_match = not tag or f"#{tag}" in content
            
            if keyword_match and tag_match:
                # Extract title
                title = md_file.stem
                first_line = content.split('\n')[0]
                if first_line.startswith('#'):
                    title = first_line.lstrip('#').strip()
                
                # Extract context
                context = ""
                if keyword:
                    pattern = re.compile(r'.{0,50}' + re.escape(keyword) + r'.{0,50}', re.IGNORECASE)
                    matches = pattern.findall(content)
                    if matches:
                        context = " ... ".join(matches[:2])
                
                results.append({
                    'path': str(md_file.relative_to(base_path)),
                    'title': title,
                    'context': context[:200] if context else "No context available"
                })
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Search the knowledge base')
    parser.add_argument('keyword', nargs='?', default='', help='Search keyword')
    parser.add_argument('--type', '-t', choices=['experience', 'principles', 'all'], default='all', help='Search type')
    parser.add_argument('--tag', '-T', default=None, help='Filter by tag')
    parser.add_argument('--base-path', default='memory_knowledge', help='Knowledge base root path')
    
    args = parser.parse_args()
    
    base_path = Path(args.base_path)
    
    if not args.keyword and not args.tag:
        parser.error("Please provide a keyword or tag to search")
    
    results = search_files(base_path, args.keyword, args.type, args.tag)
    
    if not results:
        print("No matching documents found")
        return
    
    print(f"Found {len(results)} result(s):\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   Path: {r['path']}")
        print(f"   Context: {r['context'][:100]}...")
        print()


if __name__ == '__main__':
    main()
