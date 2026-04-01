#!/usr/bin/env python3
"""
Create a new principle document and update the index.

Usage:
    python add_principle.py <name> [options]

Options:
    --rule, -r      Rule description
    --reason, -R    Why this rule exists
    --example, -e   Example usage (optional)
    --tags, -t      Comma-separated tags

Example:
    python add_principle.py "no-blocking-io-on-ui-thread" --rule "Never perform blocking IO on UI thread" --reason "Causes UI freeze and poor UX" --tags "performance,ui,async"
"""

import argparse
import re
from pathlib import Path


def slugify(name: str) -> str:
    """Convert name to filename-friendly format."""
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)
    return slug


def create_principle_doc(base_path: Path, name: str, rule: str = "", reason: str = "", 
                         example: str = "", tags: list = None):
    """Create a principle document."""
    slug = slugify(name)
    filename = f"{slug}.md"
    filepath = base_path / "base" / "principles" / filename
    
    if filepath.exists():
        print(f"[Warning] File already exists: {filepath}")
        return None
    
    tag_str = " ".join(f"#{t}" for t in (tags or ["principle"]))
    
    rule_text = rule or "Rule description pending"
    reason_text = reason or "Reason pending"
    example_text = example or "```python\n# Example code\n```"
    
    content = f"""# {name}

## Rule
{rule_text}

## Reason
{reason_text}

## Example
{example_text}

## Tags
{tag_str}
"""
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding='utf-8')
    print(f"[Created] {filepath}")
    
    return filename


def update_index(base_path: Path, filename: str, name: str, rule: str, tags: list = None):
    """Update the index file."""
    index_path = base_path / "base" / "principles" / "INDEX.md"
    
    desc = (rule or name)[:30] + ("..." if len(rule or name) > 30 else "")
    tag_str = " ".join(f"#{t}" for t in (tags or ["principle"]))
    new_entry = f"| [{filename}]({filename}) | {desc} | {tag_str} |"
    
    if index_path.exists():
        content = index_path.read_text(encoding='utf-8')
        lines = content.rstrip().split('\n')
        insert_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith('|'):
                insert_idx = i + 1
                break
        lines.insert(insert_idx, new_entry)
        index_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f"[Updated] {index_path}")
    else:
        content = f"""# Principles Index

> Auto-generated. Update this file when adding new principles.

| File | Description | Tags |
|------|-------------|------|
{new_entry}"""
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(content, encoding='utf-8')
        print(f"[Created] {index_path}")


def main():
    parser = argparse.ArgumentParser(description='Create a new principle document')
    parser.add_argument('name', help='Principle name (used for filename)')
    parser.add_argument('--rule', '-r', default='', help='Rule description')
    parser.add_argument('--reason', '-R', default='', help='Why this rule exists')
    parser.add_argument('--example', '-e', default='', help='Example usage')
    parser.add_argument('--tags', '-t', default='', help='Comma-separated tags')
    parser.add_argument('--base-path', default='memory_knowledge', help='Knowledge base root path')
    
    args = parser.parse_args()
    
    base_path = Path(args.base_path)
    tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else None
    
    filename = create_principle_doc(base_path, args.name, args.rule, args.reason, args.example, tags)
    if filename:
        update_index(base_path, filename, args.name, args.rule, tags)
        print(f"\n[Done] Principle document created successfully")


if __name__ == '__main__':
    main()
