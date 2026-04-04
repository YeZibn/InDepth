#!/usr/bin/env python3
"""
Add a new principle entry
"""

import sys
import os
import argparse
import re
from datetime import datetime

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    ensure_directories, get_principle_dir, generate_principle_filename,
    update_index
)


def load_template() -> str:
    """Load principle template from bundled assets."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'assets',
        'templates',
        'principle_template.md'
    )
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


def get_template(title: str, category: str, priority: str, content: str = "") -> str:
    """Generate principle markdown content"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    template = load_template()
    return template.format(
        date=date_str,
        category=category,
        priority=priority,
        title=title,
        definition=content if content else 'Clear statement of the rule or guideline',
        rationale='Why this principle is important',
        application='When and how to apply this principle',
        examples='Concrete examples of the principle in practice',
        exceptions='Cases where this principle may not apply',
        references='Related documentation, links, or resources',
    )


def replace_section(markdown: str, section_name: str, content: str) -> str:
    """Replace a markdown H2 section body while preserving document structure."""
    pattern = re.compile(
        rf"(^## {re.escape(section_name)}\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL
    )
    replacement = rf"\1{content.strip()}\n\n"
    if pattern.search(markdown):
        return pattern.sub(replacement, markdown, count=1)
    return markdown.rstrip() + f"\n\n## {section_name}\n{content.strip()}\n"


def main():
    parser = argparse.ArgumentParser(
        description='Add a new principle entry to memory knowledge'
    )
    parser.add_argument('title', help='Title of the principle')
    parser.add_argument('--category', '-c', 
                       choices=['coding-style', 'architecture', 'security', 'performance', 'workflow', 'testing'],
                       default='architecture',
                       help='Category of the principle')
    parser.add_argument('--priority', '-p',
                       choices=['high', 'medium', 'low'],
                       default='medium',
                       help='Priority level')
    parser.add_argument('--content', '-b',
                       help='Definition content (optional, opens editor if not provided)')
    parser.add_argument('--update', '-u',
                       action='store_true',
                       help='Update existing entry if found (instead of failing)')
    
    args = parser.parse_args()
    
    # Ensure directories exist
    ensure_directories()
    
    # Generate content
    content = args.content if args.content else ""
    
    # Generate filename
    filename = generate_principle_filename(args.title, args.category)
    filepath = os.path.join(get_principle_dir(), filename)
    
    # Check if file already exists
    if os.path.exists(filepath):
        if not args.update:
            print(f"Error: File already exists: {filepath}")
            print("Use --update to modify the existing entry, or use a different title.")
            sys.exit(1)

        # Update existing entry
        if args.content:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = f.read()
            updated = replace_section(existing, 'Definition', args.content)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(updated)
            print(f"✓ Principle updated: {filepath}")
            print("  Updated section: Definition")
            update_index('principle')
            print("✓ Index updated")
            return

        editor = os.environ.get('EDITOR', 'vi')
        print(f"Opening existing entry in editor: {filepath}")
        os.system(f'{editor} "{filepath}"')
        return
    
    # Generate markdown content
    markdown = get_template(args.title, args.category, args.priority, content)
    
    # Write file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    print(f"✓ Principle created: {filepath}")
    print(f"  Title: {args.title}")
    print(f"  Category: {args.category}")
    print(f"  Priority: {args.priority}")
    
    # Update index
    update_index('principle')
    print(f"✓ Index updated")
    
    # Open in editor if no content provided
    if not args.content:
        editor = os.environ.get('EDITOR', 'vi')
        print(f"\nOpening in editor...")
        os.system(f'{editor} "{filepath}"')


if __name__ == "__main__":
    main()
