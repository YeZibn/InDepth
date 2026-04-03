#!/usr/bin/env python3
"""
List memory knowledge entries
"""

import sys
import os
import argparse

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import list_memories, ensure_directories


def main():
    parser = argparse.ArgumentParser(
        description='List memory knowledge entries'
    )
    parser.add_argument('--type', '-t',
                       choices=['experience', 'principle'],
                       help='Filter by memory type')
    parser.add_argument('--category', '-c',
                       help='Filter by category')
    parser.add_argument('--sort', '-s',
                       choices=['date', 'title', 'category'],
                       default='date',
                       help='Sort order (default: date)')
    parser.add_argument('--limit', '-l',
                       type=int,
                       default=50,
                       help='Maximum number of results (default: 50)')
    
    args = parser.parse_args()
    
    # Ensure directories exist
    ensure_directories()
    
    # Get memories
    memories = list_memories(args.type)
    
    # Filter by category if specified
    if args.category:
        memories = [m for m in memories if m.get('category') == args.category]
    
    # Sort
    if args.sort == 'date':
        memories.sort(key=lambda x: x.get('date') or '', reverse=True)
    elif args.sort == 'title':
        memories.sort(key=lambda x: x.get('title', '').lower())
    elif args.sort == 'category':
        memories.sort(key=lambda x: (x.get('category', ''), x.get('date', '')))
    
    if not memories:
        print("No memories found.")
        if args.type:
            print(f"  Type: {args.type}")
        if args.category:
            print(f"  Category: {args.category}")
        return
    
    # Display results
    total = len(memories)
    display_count = min(total, args.limit)
    
    type_label = args.type.title() if args.type else "Memory"
    print(f"\n{type_label} Entries ({total} total):")
    print("=" * 80)
    
    # Group by category for better readability
    current_category = None
    
    for memory in memories[:args.limit]:
        memory_type = memory.get('type', 'unknown')
        category = memory.get('category', 'uncategorized')
        title = memory.get('title', 'Untitled')
        date = memory.get('date', '')
        priority = memory.get('priority', '')
        filename = memory.get('filename', '')
        
        # Print category header if changed
        if args.sort == 'category' and category != current_category:
            current_category = category
            print(f"\n## {category.title()}")
        
        # Build info string
        info_parts = []
        if date:
            info_parts.append(date)
        if priority:
            info_parts.append(f"priority: {priority}")
        
        print(f"\n  {title}")
        if info_parts:
            print(f"    {' | '.join(info_parts)}")
        print(f"    [{memory_type}] {filename}")
    
    if total > args.limit:
        print(f"\n... and {total - args.limit} more entries")
    
    print("\n" + "=" * 80)
    print(f"Showing {display_count} of {total} entr{'y' if total == 1 else 'ies'}")
    
    # Show index file location
    if args.type == 'experience':
        from utils import get_experience_dir
        index_path = os.path.join(get_experience_dir(), 'INDEX.md')
        print(f"\nSee also: {index_path}")
    elif args.type == 'principle':
        from utils import get_principle_dir
        index_path = os.path.join(get_principle_dir(), 'INDEX.md')
        print(f"\nSee also: {index_path}")


if __name__ == "__main__":
    main()
