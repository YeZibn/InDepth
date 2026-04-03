#!/usr/bin/env python3
"""
Memory Knowledge Skill Utilities
Helper functions for memory management
"""

import os
import re
import glob
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def find_project_root() -> str:
    """
    Find the project root directory by looking for characteristic directories.
    
    Searches upward from the current script location for:
    1. Directory containing '.git' folder
    2. Directory containing 'app/skills' folder structure
    
    Returns:
        Absolute path to the project root directory
    """
    # Start from the directory containing this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Search upward until we find the project root markers
    while current_dir != os.path.dirname(current_dir):  # Stop at filesystem root
        # Check for .git directory (primary marker)
        if os.path.isdir(os.path.join(current_dir, '.git')):
            return current_dir
        
        # Check for app/skills directory structure (secondary marker)
        if os.path.isdir(os.path.join(current_dir, 'app', 'skills')):
            return current_dir
        
        # Move up one directory
        current_dir = os.path.dirname(current_dir)
    
    # Fallback: if no markers found, use the script's grandparent directory
    # (scripts/ -> memory-knowledge-skill/ -> skills/ -> app/ -> project_root)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))


def get_project_root() -> str:
    """Get the cached project root directory"""
    if not hasattr(get_project_root, '_cached'):
        get_project_root._cached = find_project_root()
    return get_project_root._cached


def get_memory_knowledge_dir() -> str:
    """Get the memory-knowledge directory path"""
    return os.path.join(get_project_root(), 'memory-knowledge')


def get_experience_dir() -> str:
    """Get the experience directory path"""
    return os.path.join(get_memory_knowledge_dir(), 'experience')


def get_principle_dir() -> str:
    """Get the principle directory path"""
    return os.path.join(get_memory_knowledge_dir(), 'principle')


def ensure_directories() -> None:
    """Ensure all required directories exist"""
    dirs = [
        get_memory_knowledge_dir(),
        get_experience_dir(),
        get_principle_dir(),
    ]
    for dir_path in dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)


def sanitize_filename(name: str) -> str:
    """Convert a title to a safe filename"""
    # Replace spaces with hyphens
    sanitized = name.lower().replace(' ', '-')
    # Remove special characters
    sanitized = re.sub(r'[^a-z0-9\-]', '', sanitized)
    # Remove multiple consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    return sanitized


def parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """Parse YAML frontmatter from markdown content"""
    frontmatter = {}
    body = content
    
    # Check for frontmatter delimiters
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
                
                # Convert date objects to strings for consistent handling
                if 'date' in frontmatter and hasattr(frontmatter['date'], 'strftime'):
                    frontmatter['date'] = frontmatter['date'].strftime('%Y-%m-%d')
                if 'created' in frontmatter and hasattr(frontmatter['created'], 'strftime'):
                    frontmatter['created'] = frontmatter['created'].strftime('%Y-%m-%d')
                    
            except yaml.YAMLError:
                pass
    
    return frontmatter, body


def parse_memory_file(filepath: str) -> Optional[Dict]:
    """Parse a memory markdown file and return structured data"""
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    frontmatter, body = parse_frontmatter(content)
    
    # Extract title from first # heading
    title_match = re.search(r'^# (.+)$', body, re.MULTILINE)
    title = title_match.group(1) if title_match else os.path.basename(filepath)
    
    return {
        'filepath': filepath,
        'filename': os.path.basename(filepath),
        'frontmatter': frontmatter,
        'title': title,
        'body': body,
        'type': frontmatter.get('type', 'unknown'),
        'category': frontmatter.get('category', 'unknown'),
        'date': frontmatter.get('date') or frontmatter.get('created'),
        'tags': frontmatter.get('tags', []),
        'priority': frontmatter.get('priority', 'medium'),
    }


def list_memories(memory_type: Optional[str] = None) -> List[Dict]:
    """List all memory files"""
    memories = []
    
    dirs = []
    if memory_type is None or memory_type == 'experience':
        dirs.append(get_experience_dir())
    if memory_type is None or memory_type == 'principle':
        dirs.append(get_principle_dir())
    
    for dir_path in dirs:
        if not os.path.exists(dir_path):
            continue
        
        pattern = os.path.join(dir_path, '*.md')
        for filepath in glob.glob(pattern):
            if os.path.basename(filepath) == 'INDEX.md':
                continue
            
            memory = parse_memory_file(filepath)
            if memory:
                memories.append(memory)
    
    # Sort by date (newest first)
    memories.sort(key=lambda x: x.get('date') or '', reverse=True)
    return memories


def search_memories(query: str, memory_type: Optional[str] = None, 
                   category: Optional[str] = None) -> List[Dict]:
    """Search memories by query string"""
    all_memories = list_memories(memory_type)
    query_lower = query.lower()
    
    matching = []
    for memory in all_memories:
        # Filter by category if specified
        if category and memory.get('category') != category:
            continue
        
        # Search in title
        if query_lower in memory.get('title', '').lower():
            matching.append(memory)
            continue
        
        # Search in body
        if query_lower in memory.get('body', '').lower():
            matching.append(memory)
            continue
        
        # Search in tags
        tags = memory.get('tags', [])
        if any(query_lower in str(tag).lower() for tag in tags):
            matching.append(memory)
            continue
    
    return matching


def generate_experience_filename(title: str, date: Optional[str] = None) -> str:
    """Generate a filename for an experience entry"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    sanitized_title = sanitize_filename(title)
    return f"{date}-{sanitized_title}.md"


def generate_principle_filename(title: str, category: str) -> str:
    """Generate a filename for a principle entry"""
    sanitized_title = sanitize_filename(title)
    return f"{category}-{sanitized_title}.md"


def update_index(memory_type: str) -> None:
    """Update the INDEX.md for a memory type"""
    if memory_type == 'experience':
        dir_path = get_experience_dir()
        title = "Experience Index"
        description = "Collection of lessons learned from practice"
    elif memory_type == 'principle':
        dir_path = get_principle_dir()
        title = "Principle Index"
        description = "Collection of rules and guidelines to follow"
    else:
        return
    
    if not os.path.exists(dir_path):
        return
    
    memories = list_memories(memory_type)
    
    # Group by category
    by_category = {}
    for memory in memories:
        cat = memory.get('category', 'uncategorized')
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(memory)
    
    # Generate index content
    content = f"""# {title}

{description}

**Total entries:** {len(memories)}

**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

"""
    
    for category in sorted(by_category.keys()):
        content += f"## {category.title()}\n\n"
        for memory in by_category[category]:
            date_str = memory.get('date', '')
            title_str = memory.get('title', 'Untitled')
            filename = memory.get('filename', '')
            content += f"- [{title_str}]({filename})"
            if date_str:
                content += f" - *{date_str}*"
            content += "\n"
        content += "\n"
    
    # Write index file
    index_path = os.path.join(dir_path, 'INDEX.md')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)
