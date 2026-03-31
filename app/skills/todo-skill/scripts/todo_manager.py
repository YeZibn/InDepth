#!/usr/bin/env python3
"""
Todo Manager - 任务跟踪脚本

用法:
    python todo_manager.py create "<任务名>" "<优先级>"
    python todo_manager.py add-step <filename> "<步骤名>" [依赖步骤]
    python todo_manager.py update-step <filename> "<步骤名>" <todo|in_progress|done>
    python todo_manager.py list
    python todo_manager.py show <filename>
    python todo_manager.py done <filename>
    python todo_manager.py delete <filename>
"""

import os
import sys
import re
from datetime import datetime
from pathlib import Path


TODO_DIR = Path("todo")
TODO_DIR.mkdir(exist_ok=True)

INDEX_FILE = TODO_DIR / "INDEX.md"


def get_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


def sanitize_filename(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[\s]+', '-', name)
    return name[:50]


def parse_dependencies(content: str) -> dict:
    deps = {}
    dep_section = re.search(r'## 依赖关系\s*\n\n(.*?)(?=\n##|\n#|$)', content, re.DOTALL)
    if not dep_section:
        return deps

    lines = dep_section.group(1).strip().split('\n')
    for line in lines:
        if '|' not in line or '步骤' in line or '依赖' in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 3:
            step = parts[1]
            dependency = parts[2]
            if step and dependency:
                deps[step] = dependency

    return deps


def get_step_status(content: str, step: str) -> str:
    step_pattern = re.escape(step)
    todo_match = re.search(rf'### (?:待办|Todo)\s*\n(.*?)(?=\n###|\n##|\n#|$)', content, re.DOTALL)
    in_progress_match = re.search(rf'### (?:进行中|In Progress)\s*\n(.*?)(?=\n###|\n##|\n#|$)', content, re.DOTALL)
    done_match = re.search(rf'### (?:已完成|Done)\s*\n(.*?)(?=\n###|\n##|\n#|$)', content, re.DOTALL)

    if todo_match and re.search(rf'- \[ \]\s*{step_pattern}', todo_match.group(1)):
        return "todo"
    if in_progress_match and re.search(rf'- \[ \]\s*{step_pattern}', in_progress_match.group(1)):
        return "in_progress"
    if done_match and re.search(rf'- \[x\]\s*{step_pattern}', done_match.group(1)):
        return "done"

    return "unknown"


def check_blocked(step: str, deps: dict, content: str) -> str:
    if step not in deps:
        return ""

    dependency = deps[step]
    dep_status = get_step_status(content, dependency)

    if dep_status == "done":
        return ""
    elif dep_status == "in_progress":
        return f"（阻塞中：等待 {dependency}）"
    else:
        return f"（阻塞中：等待 {dependency}）"


def create_todo(name: str, priority: str = "中") -> str:
    timestamp = get_timestamp()
    filename = f"{timestamp}-{sanitize_filename(name)}.md"
    filepath = TODO_DIR / filename

    content = f"""# {name}

## 元信息

| 字段 | 值 |
|------|-----|
| 优先级 | {priority} |
| 创建时间 | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} |
| 状态 | 进行中 |
| 进度 | 0% |

## 依赖关系

| 步骤 | 依赖 | 说明 |
|------|------|------|

## 任务步骤

### 待办 (Todo)

### 进行中 (In Progress)

### 已完成 (Done)

## 备注
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    update_index()

    return filename


def add_step(filename: str, step: str, dependency: str = "") -> str:
    filepath = TODO_DIR / filename
    if not filepath.exists():
        return f"Error: Todo '{filename}' not found"

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    todo_section = re.search(r'(### 待办 \(Todo\)\n)', content)
    if not todo_section:
        return "Error: 未找到待办区域"

    new_step = f"- [ ] {step}"
    insert_pos = todo_section.end()
    content = content[:insert_pos] + new_step + "\n" + content[insert_pos:]

    if dependency:
        dep_table = re.search(r'(\| 步骤 \| 依赖 \| 说明 \|\n\|------\|------\|------\|\n)', content)
        if dep_table:
            dep_line = f"| {step} | {dependency} | |\n"
            insert_pos = dep_table.end()
            content = content[:insert_pos] + dep_line + content[insert_pos:]

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    update_index()

    return f"Added step: {step}"


def update_step(filename: str, step: str, status: str) -> str:
    filepath = TODO_DIR / filename
    if not filepath.exists():
        return f"Error: Todo '{filename}' not found"

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    step_pattern = re.escape(step)
    status = status.lower()

    sections = [
        ('### 待办 (Todo)', r'- \[ \]\s*' + step_pattern),
        ('### 进行中 (In Progress)', r'- \[ \]\s*' + step_pattern),
        ('### 已完成 (Done)', r'- \[x\]\s*' + step_pattern),
    ]

    for section_name, pattern in sections:
        section_match = re.search(rf'{section_name}\n(.*?)(?=\n###|\n##|\n#|$)', content, re.DOTALL)
        if section_match and re.search(pattern, section_match.group(1)):
            if status == 'done':
                new_pattern = '- [x] ' + step
            elif status == 'in_progress':
                new_pattern = '- [ ] ' + step
            else:
                new_pattern = '- [ ] ' + step

            content = re.sub(pattern, new_pattern, section_match.group(1))
            old_section = section_match.group(0)
            new_section = section_match.group(0).replace(section_match.group(1).strip(), new_pattern)

            section_start = content.find(old_section)
            if section_start != -1:
                content = content[:section_start] + new_section + content[section_start + len(old_section):]

            if status == 'in_progress':
                in_progress_section = re.search(r'(### 进行中 \(In Progress\)\n)', content)
                if in_progress_section:
                    target_in_progress = re.search(rf'{section_name}\n(.*?)(?=\n###|\n##|\n#|$)', content, re.DOTALL)
                    if target_in_progress:
                        lines = target_in_progress.group(1).strip().split('\n')
                        new_lines = []
                        for line in lines:
                            if step in line:
                                deps = parse_dependencies(content)
                                block_info = check_blocked(step, deps, content)
                                if block_info:
                                    line = line.replace('- [ ]', f'- [ ] {block_info}')
                                new_lines.append(line)
                            else:
                                new_lines.append(line)
                        new_content = '\n'.join(new_lines)
                        content = content.replace(target_in_progress.group(1), new_content)

            break

    progress = calculate_progress(filepath, content)
    content = re.sub(r'\| 进度\s*\|.*?\|', f'| 进度 | {progress}% |', content)

    if status == 'done':
        content = re.sub(r'\| 状态\s*\|.*?\|', '| 状态 | 进行中 |', content)
        remaining = count_remaining_steps(content)
        if remaining == 0:
            content = re.sub(r'\| 状态\s*\|.*?\|', '| 状态 | 已完成 |', content)
            content = re.sub(r'\| 进度\s*\|.*?\|', '| 进度 | 100% |', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    update_index()

    return f"Updated {step} to {status}"


def count_remaining_steps(content: str) -> int:
    todo_match = re.findall(r'- \[ \]', content)
    return len(todo_match)


def calculate_progress(filepath: Path, content: str = None) -> int:
    if content is None:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

    todo_match = re.findall(r'- \[ \]', content)
    done_match = re.findall(r'- \[x\]', content)

    total = len(todo_match) + len(done_match)
    if total == 0:
        return 0

    return int(len(done_match) / total * 100)


def list_todos() -> list:
    todos = []
    for f in sorted(TODO_DIR.glob("*.md"), reverse=True):
        if f.name == "INDEX.md":
            continue
        todos.append(f.name)
    return todos


def show_todo(filename: str) -> str:
    filepath = TODO_DIR / filename
    if not filepath.exists():
        return f"Error: Todo '{filename}' not found"
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def done_todo(filename: str) -> str:
    filepath = TODO_DIR / filename
    if not filepath.exists():
        return f"Error: Todo '{filename}' not found"

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    content = re.sub(
        r'\| 状态\s*\|.*?\|',
        '| 状态 | 已完成 |',
        content
    )
    content = re.sub(
        r'\| 进度\s*\|.*?\|',
        '| 进度 | 100% |',
        content
    )

    content_lines = content.split('\n')
    new_lines = []
    in_todo_section = False

    for line in content_lines:
        if '### 待办 (Todo)' in line or '### 进行中 (In Progress)' in line:
            in_todo_section = True
            new_lines.append(line)
        elif in_todo_section and line.startswith('###'):
            in_todo_section = False
            new_lines.append(line)
        elif in_todo_section and '- [ ]' in line:
            new_lines.append(line.replace('- [ ]', '- [x]'))
        else:
            new_lines.append(line)

    content = '\n'.join(new_lines)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    update_index()

    return f"Todo '{filename}' marked as done"


def delete_todo(filename: str) -> str:
    filepath = TODO_DIR / filename
    if not filepath.exists():
        return f"Error: Todo '{filename}' not found"

    filepath.unlink()
    update_index()

    return f"Todo '{filename}' deleted"


def get_blocked_reason(filepath: Path) -> str:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    deps = parse_dependencies(content)

    in_progress_section = re.search(r'### 进行中 \(In Progress\)\n(.*?)(?=\n###|\n##|\n#|$)', content, re.DOTALL)
    if not in_progress_section:
        return ""

    lines = in_progress_section.group(1).strip().split('\n')
    for line in lines:
        if '- [ ]' in line and '（阻塞中' in line:
            match = re.search(r'（阻塞中：等待 (.+?)）', line)
            if match:
                blocked_by = match.group(1)
                dep_status = get_step_status(content, blocked_by)
                return f"等待 {blocked_by}"

    return ""


def update_index():
    todos = []
    for f in sorted(TODO_DIR.glob("*.md"), reverse=True):
        if f.name == "INDEX.md":
            continue

        with open(f, 'r', encoding='utf-8') as fp:
            content = fp.read()

        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        priority_match = re.search(r'\| 优先级\s*\|\s*(.+?)\s*\|', content)
        status_match = re.search(r'\| 状态\s*\|\s*(.+?)\s*\|', content)
        progress_match = re.search(r'\| 进度\s*\|\s*(.+?)\s*\|', content)

        title = title_match.group(1) if title_match else f.name
        priority = priority_match.group(1) if priority_match else "中"
        status = status_match.group(1) if status_match else "进行中"
        progress = progress_match.group(1) if progress_match else "0%"

        blocked_reason = get_blocked_reason(f) if status == "进行中" else ""

        todos.append({
            'file': f.name,
            'title': title,
            'priority': priority,
            'status': status,
            'progress': progress,
            'blocked': blocked_reason
        })

    in_progress = [t for t in todos if t['status'] == '进行中' and not t['blocked']]
    blocked = [t for t in todos if t['status'] == '进行中' and t['blocked']]
    completed = [t for t in todos if t['status'] == '已完成']

    index_content = "# Todo 索引\n\n"

    if in_progress:
        index_content += "## 进行中\n\n"
        index_content += "| 文件 | 任务 | 优先级 | 进度 |\n"
        index_content += "|------|------|--------|------|\n"
        for t in in_progress:
            index_content += f"| [{t['file']}]({t['file']}) | {t['title']} | {t['priority']} | {t['progress']} |\n"
        index_content += "\n"

    if blocked:
        index_content += "## 阻塞中\n\n"
        index_content += "| 文件 | 任务 | 等待 |\n"
        index_content += "|------|------|------|\n"
        for t in blocked:
            index_content += f"| [{t['file']}]({t['file']}) | {t['title']} | {t['blocked']} |\n"
        index_content += "\n"

    if completed:
        index_content += "## 已完成\n\n"
        index_content += "| 文件 | 任务 | 完成时间 |\n"
        index_content += "|------|------|----------|\n"
        for t in completed:
            index_content += f"| [{t['file']}]({t['file']}) | {t['title']} | {datetime.now().strftime('%Y-%m-%d')} |\n"

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(index_content)


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python todo_manager.py create <任务名> [优先级]")
        print("  python todo_manager.py add-step <filename> <步骤名> [依赖步骤]")
        print("  python todo_manager.py update-step <filename> <步骤名> <todo|in_progress|done>")
        print("  python todo_manager.py list")
        print("  python todo_manager.py show <filename>")
        print("  python todo_manager.py done <filename>")
        print("  python todo_manager.py delete <filename>")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "create":
        if len(sys.argv) < 3:
            print("Error: 请提供任务名称")
            sys.exit(1)
        name = sys.argv[2]
        priority = sys.argv[3] if len(sys.argv) > 3 else "中"
        result = create_todo(name, priority)
        print(f"Created: {result}")

    elif command == "add-step":
        if len(sys.argv) < 4:
            print("Error: 请提供文件名和步骤名")
            sys.exit(1)
        filename = sys.argv[2]
        step = sys.argv[3]
        dependency = sys.argv[4] if len(sys.argv) > 4 else ""
        print(add_step(filename, step, dependency))

    elif command == "update-step":
        if len(sys.argv) < 5:
            print("Error: 请提供文件名、步骤名和状态")
            sys.exit(1)
        filename = sys.argv[2]
        step = sys.argv[3]
        status = sys.argv[4]
        print(update_step(filename, step, status))

    elif command == "list":
        todos = list_todos()
        if not todos:
            print("No todos found")
        else:
            for t in todos:
                print(f"  - {t}")

    elif command == "show":
        if len(sys.argv) < 3:
            print("Error: 请提供文件名")
            sys.exit(1)
        print(show_todo(sys.argv[2]))

    elif command == "done":
        if len(sys.argv) < 3:
            print("Error: 请提供文件名")
            sys.exit(1)
        print(done_todo(sys.argv[2]))

    elif command == "delete":
        if len(sys.argv) < 3:
            print("Error: 请提供文件名")
            sys.exit(1)
        print(delete_todo(sys.argv[2]))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
