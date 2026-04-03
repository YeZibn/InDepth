#!/usr/bin/env python3
"""
Test script for create_task.py intelligent subtask parsing
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil

def run_create_task(task_name, context, subtasks_arg=None):
    """Run create_task.py with given arguments"""
    cmd = ['python3', 'scripts/create_task.py', task_name, context]
    if subtasks_arg:
        cmd.append(subtasks_arg)
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd='/root/github/InDepth/app/skills/todo-skill')
    return result.returncode, result.stdout, result.stderr

def read_task_file(filepath):
    """Read and return task file content"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def cleanup_test_files():
    """Remove test task files"""
    todo_dir = '/root/github/InDepth/todo'
    if not os.path.exists(todo_dir):
        return
    for filename in os.listdir(todo_dir):
        if 'test_task' in filename or 'Test_Task' in filename:
            filepath = os.path.join(todo_dir, filename)
            os.remove(filepath)
            print(f"Cleaned up: {filepath}")

def test_json_subtasks():
    """Test creating task with JSON subtasks"""
    print("\n" + "="*60)
    print("TEST 1: JSON format subtasks")
    print("="*60)
    
    subtasks_json = json.dumps([
        {
            "name": "搜索全球科技领域重要新闻",
            "description": "通过搜索获取近一个月全球科技领域的重要新闻",
            "priority": "high",
            "dependencies": []
        },
        {
            "name": "搜索国内科技领域重要新闻",
            "description": "通过搜索获取近一个月国内科技领域的重要新闻",
            "priority": "high",
            "dependencies": []
        },
        {
            "name": "筛选核心新闻",
            "description": "从搜索结果中筛选核心新闻",
            "priority": "high",
            "dependencies": ["1", "2"]
        }
    ])
    
    returncode, stdout, stderr = run_create_task(
        "Test Task JSON",
        "Test context for JSON subtasks",
        subtasks_json
    )
    
    print(f"Return code: {returncode}")
    print(f"Output: {stdout}")
    if stderr:
        print(f"Errors: {stderr}")
    
    if returncode != 0:
        print("❌ FAILED: Script returned non-zero exit code")
        return False
    
    if "✅ Task created" not in stdout:
        print("❌ FAILED: Success message not found")
        return False
    
    lines = stdout.strip().split('\n')
    filepath_line = [l for l in lines if 'Task created:' in l]
    if not filepath_line:
        print("❌ FAILED: File path not found in output")
        return False
    
    filepath = filepath_line[0].replace("✅ Task created:", "").strip()
    
    content = read_task_file(filepath)
    if not content:
        print("❌ FAILED: Task file not created")
        return False
    
    print("\nTask file content preview:")
    print("-" * 60)
    print(content[:500])
    print("-" * 60)
    
    if "搜索全球科技领域重要新闻" not in content:
        print("❌ FAILED: Subtask name not found in file")
        return False
    
    if "**Progress**: 0/3 (0%)" not in content:
        print("❌ FAILED: Progress not correctly calculated")
        return False
    
    if "**Dependencies**: Task 1, Task 2" not in content:
        print("❌ FAILED: Dependencies not correctly formatted")
        return False
    
    print("✅ PASSED: JSON subtasks test")
    return True

def test_comma_separated():
    """Test creating task with comma-separated subtasks"""
    print("\n" + "="*60)
    print("TEST 2: Comma-separated subtasks (auto-split)")
    print("="*60)
    
    comma_separated = "Design the research plan,Search for global tech news,Search for China tech news,Filter core news,Write analysis,Output document"
    
    returncode, stdout, stderr = run_create_task(
        "Test Task Comma",
        "Test context for comma-separated subtasks",
        comma_separated
    )
    
    print(f"Return code: {returncode}")
    print(f"Output: {stdout}")
    if stderr:
        print(f"Errors: {stderr}")
    
    if returncode != 0:
        print("❌ FAILED: Script returned non-zero exit code")
        return False
    
    if "ℹ️  Detected comma-separated format" not in stdout:
        print("❌ FAILED: Auto-detection message not found")
        return False
    
    if "Subtasks: 6" not in stdout:
        print("❌ FAILED: Incorrect number of subtasks")
        return False
    
    lines = stdout.strip().split('\n')
    filepath_line = [l for l in lines if 'Task created:' in l]
    filepath = filepath_line[0].replace("✅ Task created:", "").strip()
    
    content = read_task_file(filepath)
    if not content:
        print("❌ FAILED: Task file not created")
        return False
    
    print("\nTask file content preview:")
    print("-" * 60)
    print(content[:800])
    print("-" * 60)
    
    if "**Progress**: 0/6 (0%)" not in content:
        print("❌ FAILED: Progress not correctly calculated for 6 subtasks")
        return False
    
    if "Design the research plan" not in content:
        print("❌ FAILED: First subtask not found")
        return False
    
    if "Output document" not in content:
        print("❌ FAILED: Last subtask not found")
        return False
    
    print("✅ PASSED: Comma-separated subtasks test")
    return True

def test_multiple_args():
    """Test creating task with multiple arguments"""
    print("\n" + "="*60)
    print("TEST 3: Multiple arguments")
    print("="*60)
    
    cmd = ['python3', 'scripts/create_task.py', 'Test Task Multi', 'Test context', 
           'Step 1 description', 'Step 2 description', 'Step 3 description']
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd='/root/github/InDepth/app/skills/todo-skill')
    
    print(f"Return code: {result.returncode}")
    print(f"Output: {result.stdout}")
    if result.stderr:
        print(f"Errors: {result.stderr}")
    
    if result.returncode != 0:
        print("❌ FAILED: Script returned non-zero exit code")
        return False
    
    if "Subtasks: 3" not in result.stdout:
        print("❌ FAILED: Incorrect number of subtasks")
        return False
    
    lines = result.stdout.strip().split('\n')
    filepath_line = [l for l in lines if 'Task created:' in l]
    filepath = filepath_line[0].replace("✅ Task created:", "").strip()
    
    content = read_task_file(filepath)
    if not content:
        print("❌ FAILED: Task file not created")
        return False
    
    print("\nTask file content preview:")
    print("-" * 60)
    print(content[:600])
    print("-" * 60)
    
    if "Step 1 description" not in content:
        print("❌ FAILED: Subtask description not found")
        return False
    
    print("✅ PASSED: Multiple arguments test")
    return True

def test_default_subtasks():
    """Test creating task with default subtasks"""
    print("\n" + "="*60)
    print("TEST 4: Default subtasks (no arguments)")
    print("="*60)
    
    returncode, stdout, stderr = run_create_task(
        "Test Task Default",
        "Test context for default subtasks"
    )
    
    print(f"Return code: {returncode}")
    print(f"Output: {stdout}")
    if stderr:
        print(f"Errors: {stderr}")
    
    if returncode != 0:
        print("❌ FAILED: Script returned non-zero exit code")
        return False
    
    if "Subtasks: 4" not in stdout:
        print("❌ FAILED: Incorrect number of default subtasks")
        return False
    
    lines = stdout.strip().split('\n')
    filepath_line = [l for l in lines if 'Task created:' in l]
    filepath = filepath_line[0].replace("✅ Task created:", "").strip()
    
    content = read_task_file(filepath)
    if not content:
        print("❌ FAILED: Task file not created")
        return False
    
    print("\nTask file content preview:")
    print("-" * 60)
    print(content[:600])
    print("-" * 60)
    
    if "Initial Setup" not in content:
        print("❌ FAILED: Default subtask not found")
        return False
    
    if "**Progress**: 0/4 (0%)" not in content:
        print("❌ FAILED: Default progress not correct")
        return False
    
    print("✅ PASSED: Default subtasks test")
    return True

def test_invalid_json():
    """Test error handling for invalid JSON"""
    print("\n" + "="*60)
    print("TEST 5: Invalid JSON handling")
    print("="*60)
    
    invalid_json = "[{invalid json}]"
    
    returncode, stdout, stderr = run_create_task(
        "Test Task Invalid",
        "Test context",
        invalid_json
    )
    
    print(f"Return code: {returncode}")
    print(f"Output: {stdout}")
    if stderr:
        print(f"Errors: {stderr}")
    
    if returncode == 0:
        print("❌ FAILED: Script should return non-zero for invalid JSON")
        return False
    
    if "Invalid JSON format" not in stdout and "Invalid JSON format" not in stderr:
        print("❌ FAILED: Expected JSON error message not found")
        return False
    
    print("✅ PASSED: Invalid JSON error handling test")
    return True

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("TESTING CREATE_TASK.PY INTELLIGENT PARSING")
    print("="*60)
    
    cleanup_test_files()
    
    tests = [
        test_json_subtasks,
        test_comma_separated,
        test_multiple_args,
        test_default_subtasks,
        test_invalid_json
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    cleanup_test_files()
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ ALL TESTS PASSED!")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
