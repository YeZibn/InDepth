#!/usr/bin/env python3
"""
Add a new principle entry
"""

import sys
import os
import argparse
from datetime import datetime

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    ensure_directories, get_principle_dir, generate_principle_filename,
    update_index
)


def get_template(title: str, category: str, priority: str, content: str = "") -> str:
    """Generate principle markdown content"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    template = f"""---
type: principle
category: {category}
priority: {priority}
created: {date_str}
---

# {title}

## Definition
{content if content else 'Clear statement of the rule or guideline'}

## Rationale
Why this principle is important

## Application
When and how to apply this principle

### Examples
Concrete examples of the principle in practice

## Exceptions
Cases where this principle may not apply

## References
Related documentation, links, or resources
"""
    return template


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
        print(f"Error: File already exists: {filepath}")
        print("Use a different title.")
        sys.exit(1)
    
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
