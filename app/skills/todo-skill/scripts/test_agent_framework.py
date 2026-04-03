#!/usr/bin/env python3
"""
Test the main_from_args_list function for agent framework compatibility
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_task import main_from_args_list

def cleanup_test_files():
    """Remove test task files"""
    todo_dir = '/root/github/InDepth/todo'
    if not os.path.exists(todo_dir):
        return
    for filename in os.listdir(todo_dir):
        if 'test' in filename.lower() or '科技调研' in filename:
            filepath = os.path.join(todo_dir, filename)
            os.remove(filepath)
            print(f"Cleaned up: {filepath}")

def test_json_string_args():
    """Test with JSON string as args (simulating agent framework call)"""
    print("\n" + "="*60)
    print("TEST: JSON string args (agent framework format)")
    print("="*60)
    
    args_json = json.dumps([
        "科技调研202604",
        "科技领域新闻调研",
        json.dumps([
            {"name": "设计调研计划", "description": "确定调研方向", "priority": "high", "dependencies": []},
            {"name": "搜索全球新闻", "description": "搜索全球科技新闻", "priority": "high", "dependencies": []},
            {"name": "搜索国内新闻", "description": "搜索国内科技新闻", "priority": "high", "dependencies": []},
            {"name": "筛选核心新闻", "description": "筛选重要新闻", "priority": "high", "dependencies": ["2", "3"]},
            {"name": "撰写分析报告", "description": "撰写调研报告", "priority": "high", "dependencies": ["4"]},
            {"name": "输出文档", "description": "输出到work目录", "priority": "high", "dependencies": ["5"]}
        ])
    ])
    
    print(f"Input args (JSON string): {args_json[:100]}...")
    
    result = main_from_args_list(args_json)
    
    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    if result['success']:
        print("✅ PASSED: JSON string args test")
        return True
    else:
        print(f"❌ FAILED: {result['error']}")
        return False

def test_python_list_args():
    """Test with Python list as args"""
    print("\n" + "="*60)
    print("TEST: Python list args")
    print("="*60)
    
    args_list = [
        "Test Task",
        "Test context",
        "Step 1,Step 2,Step 3"
    ]
    
    print(f"Input args (Python list): {args_list}")
    
    result = main_from_args_list(args_list)
    
    print(f"\nResult: {json.dumps(result, indent=2)}")
    
    if result['success'] and result['subtask_count'] == 3:
        print("✅ PASSED: Python list args test")
        return True
    else:
        print(f"❌ FAILED: Expected 3 subtasks, got {result.get('subtask_count', 'N/A')}")
        return False

def test_invalid_args():
    """Test error handling for invalid args"""
    print("\n" + "="*60)
    print("TEST: Invalid args handling")
    print("="*60)
    
    result = main_from_args_list("single string")
    
    print(f"Result: {json.dumps(result, indent=2)}")
    
    if not result['success'] and 'At least task_name and context are required' in result['error']:
        print("✅ PASSED: Invalid args error handling test")
        return True
    else:
        print(f"❌ FAILED: Expected error message not found")
        return False

def main():
    print("\n" + "="*60)
    print("TESTING AGENT FRAMEWORK COMPATIBILITY")
    print("="*60)
    
    cleanup_test_files()
    
    tests = [
        test_json_string_args,
        test_python_list_args,
        test_invalid_args
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
