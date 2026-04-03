#!/usr/bin/env python3
"""
Search memory knowledge entries
"""

import sys
import os
import argparse

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import search_memories, ensure_directories


def main():
    parser = argparse.ArgumentParser(
        description='Search memory knowledge entries'
    )
    parser.add_argument('query', help='Search query')
    parser.add_argument('--type', '-t',
                       choices=['experience', 'principle'],
                       help='Filter by memory type')
    parser.add_argument('--category', '-c',
                       help='Filter by category')
    parser.add_argument('--limit', '-l',
                       type=int,
                       default=20,
                       help='Maximum number of results (default: 20)')
    
    args = parser.parse_args()
    
    # Ensure directories exist
    ensure_directories()
    
    # Search
    results = search_memories(args.query, args.type, args.category)
    
    if not results:
        print(f"No memories found for query: '{args.query}'")
        if args.type:
            print(f"  Type filter: {args.type}")
        if args.category:
            print(f"  Category filter: {args.category}")
        return
    
    # Display results
    total = len(results)
    display_count = min(total, args.limit)
    
    print(f"\nFound {total} result(s) for '{args.query}':")
    print("=" * 80)
    
    for i, memory in enumerate(results[:args.limit], 1):
        memory_type = memory.get('type', 'unknown')
        category = memory.get('category', 'unknown')
        title = memory.get('title', 'Untitled')
        date = memory.get('date', '')
        filename = memory.get('filename', '')
        
        print(f"\n[{i}] {title}")
        print(f"    Type: {memory_type} | Category: {category}", end='')
        if date:
            print(f" | Date: {date}")
        else:
            print()
        print(f"    File: {filename}")
    
    if total > args.limit:
        print(f"\n... and {total - args.limit} more results")
    
    print("\n" + "=" * 80)
    print(f"Showing {display_count} of {total} result(s)")


if __name__ == "__main__":
    main()
