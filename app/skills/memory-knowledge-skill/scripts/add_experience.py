#!/usr/bin/env python3
"""
Create a new experience document and update the index.

Usage:
    python add_experience.py <title> [options]

Options:
    --scenario, -s     Scenario or context description
    --insight, -i      Key insight or learning
    --problem, -p      Problem description (for problem-solving records)
    --solution, -S     Solution steps (for problem-solving records)
    --tags, -t         Comma-separated tags

Examples:
    python add_experience.py "Database timeout issue" --problem "Connection pool exhausted" --solution "Increased pool size" --tags "bug,fix,db"
    
    python add_experience.py "Unexpected API behavior" --scenario "API returns 429 under load" --insight "Need rate limiting on client side" --tags "api,ratelimit"
"""
import argparse
import re
from datetime import datetime
from pathlib import Path


def get_date():
    return datetime.now().strftime("%Y-%m-%d")


def slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)
    return slug[:50]


def create_experience_doc(base_path: Path, title: str, scenario: str = "", insight: str = "",
                         problem: str = "", solution: str = "", tags: list = None):
    date = get_date()
    slug = slugify(title)
    filename = f"{date}-{slug}.md"
    filepath = base_path / "base" / "experience" / filename
    
    if filepath.exists():
        print(f"[Warning] File already exists: {filepath}")
        return None
    
    tag_str = " ".join(f"#{t}" for t in (tags or ["experience"]))
    
    # Build content based on what's provided
    if problem or solution:
        # Problem-solving format
        problem_text = problem or "Problem description pending"
        solution_text = solution or "Solution steps pending"
        content = f"""# {title}

## Problem
{problem_text}

## Solution
{solution_text}

## Insight
{insight or "Key takeaways from this experience"}

## Tags
{tag_str}
"""
    else:
        # General experience format
        scenario_text = scenario or "Context pending"
        insight_text = insight or "Key insights pending"
        content = f"""# {title}

## Context
{scenario_text}

## Insight
{insight_text}

## Tags
{tag_str}
"""
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding='utf-8')
    print(f"[Created] {filepath}")
    
    return filename


def update_index(base_path: Path, filename: str, title: str, tags: list = None):
    index_path = base_path / "base" / "experience" / "INDEX.md"
    
    desc = title[:30] + ("..." if len(title) > 30 else "")
    tag_str = " ".join(f"#{t}" for t in (tags or ["experience"]))
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
        content = f"""# Experience Index

> Auto-generated. Update this file when adding new experiences.

| File | Description | Tags |
|------|-------------|------|
{new_entry}"""
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(content, encoding='utf-8')
        print(f"[Created] {index_path}")


def main():
    parser = argparse.ArgumentParser(description='Create a new experience document')
    parser.add_argument('title', help='Experience title')
    parser.add_argument('--scenario', '-s', default='', help='Scenario or context description')
    parser.add_argument('--insight', '-i', default='', help='Key insight or learning')
    parser.add_argument('--problem', '-p', default='', help='Problem description (for problem-solving)')
    parser.add_argument('--solution', '-S', default='', help='Solution steps (for problem-solving)')
    parser.add_argument('--tags', '-t', default='', help='Comma-separated tags')
    parser.add_argument('--base-path', default='memory_knowledge', help='Knowledge base root path')
    
    args = parser.parse_args()
    
    base_path = Path(args.base_path)
    tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else None
    
    filename = create_experience_doc(
        base_path, args.title,
        scenario=args.scenario, insight=args.insight,
        problem=args.problem, solution=args.solution,
        tags=tags
    )
    if filename:
        update_index(base_path, filename, args.title, tags)
        print(f"\n[Done] Experience document created successfully")


if __name__ == '__main__':
    main()
