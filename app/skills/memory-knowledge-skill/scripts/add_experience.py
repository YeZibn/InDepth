#!/usr/bin/env python3
"""
Add a new experience entry
"""

import sys
import os
import argparse
import glob
import re
from datetime import datetime

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    ensure_directories, get_experience_dir, generate_experience_filename,
    update_index, sanitize_filename
)


def load_template() -> str:
    """Load experience template from references."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'references',
        'experience_template.md'
    )
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


def get_template(
    title: str,
    category: str,
    tags: list,
    entry_date: str,
    content: str = ""
) -> str:
    """Generate experience markdown content"""
    tags_str = ', '.join(tags) if tags else ''
    template = load_template()
    return template.format(
        date=entry_date,
        category=category,
        tags=tags_str,
        title=title,
        background=content if content else 'Describe the situation or problem encountered',
        investigation='',
        solution='',
        outcome='',
        key_takeaway='',
        related_task='',
        related_code='',
        related_links='',
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


def find_existing_by_title(title: str) -> list:
    """Find existing experience files by title slug, regardless of date."""
    slug = sanitize_filename(title)
    pattern = os.path.join(get_experience_dir(), f"*-{slug}.md")
    return sorted(glob.glob(pattern))


def main():
    parser = argparse.ArgumentParser(
        description='Add a new experience entry to memory knowledge'
    )
    parser.add_argument('title', help='Title of the experience')
    parser.add_argument('--category', '-c', 
                       choices=['coding', 'debugging', 'architecture', 'performance', 'communication', 'workflow'],
                       default='coding',
                       help='Category of the experience')
    parser.add_argument('--tags', '-t', 
                       help='Comma-separated tags')
    parser.add_argument('--content', '-b',
                       help='Background content (optional, opens editor if not provided)')
    parser.add_argument('--date', '-d',
                       help='Date in YYYY-MM-DD format (default: today)')
    parser.add_argument('--update', '-u',
                       action='store_true',
                       help='Update existing entry if found (instead of failing)')
    
    args = parser.parse_args()
    
    # Ensure directories exist
    ensure_directories()
    
    # Parse tags
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(',')]
    
    # Generate content
    content = args.content if args.content else ""
    
    # Resolve and validate date to keep filename/frontmatter consistent
    date_str = args.date if args.date else datetime.now().strftime('%Y-%m-%d')
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        print(f"Error: Invalid date format '{date_str}'. Use YYYY-MM-DD.")
        sys.exit(1)

    # Generate filename
    filename = generate_experience_filename(args.title, date_str)
    filepath = os.path.join(get_experience_dir(), filename)
    
    # If update mode is enabled and exact file is not found, try title-only match.
    if args.update and not os.path.exists(filepath):
        matches = find_existing_by_title(args.title)
        if len(matches) == 1:
            filepath = matches[0]
            filename = os.path.basename(filepath)
        elif len(matches) > 1:
            print("Error: Multiple entries found for this title:")
            for m in matches:
                print(f"  - {m}")
            print("Please specify --date to update a specific file.")
            sys.exit(1)

    # Check if file already exists
    if os.path.exists(filepath):
        if not args.update:
            print(f"Error: File already exists: {filepath}")
            print("Use --update to modify the existing entry, or use a different title/date.")
            sys.exit(1)

        # Update existing entry
        if args.content:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = f.read()
            updated = replace_section(existing, 'Background', args.content)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(updated)
            print(f"✓ Experience updated: {filepath}")
            print("  Updated section: Background")
            update_index('experience')
            print("✓ Index updated")
            return

        editor = os.environ.get('EDITOR', 'vi')
        print(f"Opening existing entry in editor: {filepath}")
        os.system(f'{editor} "{filepath}"')
        return
    
    # Generate markdown content
    markdown = get_template(args.title, args.category, tags, date_str, content)
    
    # Write file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    print(f"✓ Experience created: {filepath}")
    print(f"  Title: {args.title}")
    print(f"  Category: {args.category}")
    print(f"  Tags: {', '.join(tags) if tags else 'None'}")
    
    # Update index
    update_index('experience')
    print(f"✓ Index updated")
    
    # Open in editor if no content provided
    if not args.content:
        editor = os.environ.get('EDITOR', 'vi')
        print(f"\nOpening in editor...")
        os.system(f'{editor} "{filepath}"')


if __name__ == "__main__":
    main()
