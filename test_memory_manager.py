#!/usr/bin/env python3
"""
Unit Tests for Memory Manager Agent
Tests all core functionality and edge cases
"""

import unittest
from memory_manager import MemoryManager
import os
import json


class TestMemoryManager(unittest.TestCase):
    """Test suite for Memory Manager Agent"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_file = "test_memories.json"
        self.manager = MemoryManager(storage_file=self.test_file)
    
    def tearDown(self):
        """Clean up test files"""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
    
    def test_store_memory(self):
        """Test storing a memory"""
        result = self.manager.store_memory("test1", "test value", ["tag1"])
        self.assertTrue(result)
        self.assertIn("test1", self.manager.memories)
    
    def test_retrieve_memory(self):
        """Test retrieving a stored memory"""
        self.manager.store_memory("test2", "retrieved value", [])
        value = self.manager.retrieve_memory("test2")
        self.assertEqual(value, "retrieved value")
    
    def test_retrieve_nonexistent(self):
        """Test retrieving non-existent memory"""
        value = self.manager.retrieve_memory("nonexistent")
        self.assertIsNone(value)
    
    def test_delete_memory(self):
        """Test deleting a memory"""
        self.manager.store_memory("test3", "delete me", [])
        result = self.manager.delete_memory("test3")
        self.assertTrue(result)
        self.assertNotIn("test3", self.manager.memories)
    
    def test_search_by_tag(self):
        """Test searching memories by tag"""
        self.manager.store_memory("task1", "urgent work", ["urgent"])
        self.manager.store_memory("task2", "normal work", ["normal"])
        results = self.manager.search_memories("", "urgent")
        self.assertEqual(len(results), 1)
    
    def test_list_memories(self):
        """Test listing all memories"""
        self.manager.store_memory("m1", "val1", [])
        self.manager.store_memory("m2", "val2", [])
        memories = self.manager.list_memories()
        self.assertEqual(len(memories), 2)
    
    def test_statistics(self):
        """Test getting statistics"""
        self.manager.store_memory("s1", "value", ["tag1", "tag2"])
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_memories"], 1)
        self.assertGreater(stats["total_tags"], 0)
    
    def test_save_and_load(self):
        """Test persistence - save and load"""
        self.manager.store_memory("persist", "data", [])
        self.manager.save_memories()
        
        # Create new manager and load
        new_manager = MemoryManager(storage_file=self.test_file)
        value = new_manager.retrieve_memory("persist")
        self.assertEqual(value, "data")


if __name__ == "__main__":
    unittest.main()
