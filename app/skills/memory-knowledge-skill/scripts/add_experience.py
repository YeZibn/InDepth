#!/usr/bin/env python3
"""
Add a new experience entry
"""

import sys
import os
import argparse
from datetime import datetime

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    ensure_directories, get_experience_dir, generate_experience_filename,
    update_index, sanitize_filename
)


def get_template(title: str, category: str, tags: list, content: str = "") -> str:
    """Generate experience markdown content"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    tags_str = ', '.join(tags) if tags else ''
    
    template = f"""---
type: experience
date: {date_str}
category: {category}
tags: [{tags_str}]
---

# {title}

## Background
{content if content else 'Describe the situation or problem encountered'}

## Investigation
{''}

## Solution
{''}

## Outcome
{''}

## Key Takeaway
{''}

## Related
- Task: 
- Code: 
- Links: 
"""
    return template


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
    
    args = parser.parse_args()
    
    # Ensure directories exist
    ensure_directories()
    
    # Parse tags
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(',')]
    
    # Generate content
    content = args.content if args.content else ""
    
    # Generate filename
    date_str = args.date if args.date else datetime.now().strftime('%Y-%m-%d')
    filename = generate_experience_filename(args.title, date_str)
    filepath = os.path.join(get_experience_dir(), filename)
    
    # Check if file already exists
    if os.path.exists(filepath):
        print(f"Error: File already exists: {filepath}")
        print("Use a different title or date.")
        sys.exit(1)
    
    # Generate markdown content
    markdown = get_template(args.title, args.category, tags, content)
    
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
