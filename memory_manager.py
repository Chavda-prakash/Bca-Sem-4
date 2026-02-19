#!/usr/bin/env python3
"""
Memory Manager Agent - TinyFish Implementation
A comprehensive agent for managing, storing, and retrieving memories
with persistent storage and analysis capabilities.

Author: Chavda-prakash
Version: 1.0.0
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import hashlib


class MemoryManager:
    """Core Memory Manager Agent Class"""
    
    def __init__(self, storage_file: str = "memories.json"):
        """Initialize Memory Manager with storage backend"""
        self.storage_file = storage_file
        self.memories: Dict[str, Any] = {}
        self.memory_index: Dict[str, List[str]] = {}
        self.load_memories()
    
    def store_memory(self, key: str, value: Any, tags: Optional[List[str]] = None) -> bool:
        """Store a memory with metadata"""
        try:
            memory_entry = {
                "value": value,
                "timestamp": datetime.now().isoformat(),
                "tags": tags or [],
                "hash": self._generate_hash(str(value))
            }
            self.memories[key] = memory_entry
            self._update_index(key, tags)
            self.save_memories()
            return True
        except Exception as e:
            print(f"Error storing memory: {e}")
            return False
    
    def retrieve_memory(self, key: str) -> Optional[Any]:
        """Retrieve a specific memory by key"""
        if key in self.memories:
            return self.memories[key].get("value")
        return None
    
    def search_memories(self, query: str, tag: Optional[str] = None) -> List[Dict]:
        """Search memories by query or tag"""
        results = []
        for key, memory in self.memories.items():
            if tag and tag in memory.get("tags", []):
                results.append({"key": key, "memory": memory})
            elif query.lower() in str(memory.get("value")).lower():
                results.append({"key": key, "memory": memory})
        return results
    
    def analyze_memory(self, key: str) -> Dict[str, Any]:
        """Analyze a memory entry"""
        if key not in self.memories:
            return {"error": "Memory not found"}
        
        memory = self.memories[key]
        return {
            "key": key,
            "value": memory.get("value"),
            "stored_at": memory.get("timestamp"),
            "tags": memory.get("tags", []),
            "hash": memory.get("hash"),
            "age_seconds": self._calculate_age(memory.get("timestamp"))
        }
    
    def delete_memory(self, key: str) -> bool:
        """Delete a memory entry"""
        if key in self.memories:
            del self.memories[key]
            self.save_memories()
            return True
        return False
    
    def list_memories(self, tag: Optional[str] = None) -> List[str]:
        """List all memories, optionally filtered by tag"""
        if tag:
            return [k for k, v in self.memories.items() if tag in v.get("tags", [])]
        return list(self.memories.keys())
    
    def save_memories(self) -> bool:
        """Save memories to persistent storage"""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self.memories, f, indent=2, default=str)
            return True
        except Exception as e:
            print(f"Error saving memories: {e}")
            return False
    
    def load_memories(self) -> bool:
        """Load memories from persistent storage"""
        try:
            with open(self.storage_file, 'r') as f:
                self.memories = json.load(f)
            return True
        except FileNotFoundError:
            self.memories = {}
            return True
        except Exception as e:
            print(f"Error loading memories: {e}")
            return False
    
    def _update_index(self, key: str, tags: Optional[List[str]]) -> None:
        """Update memory index for fast tag-based retrieval"""
        if tags:
            for tag in tags:
                if tag not in self.memory_index:
                    self.memory_index[tag] = []
                if key not in self.memory_index[tag]:
                    self.memory_index[tag].append(key)
    
    def _generate_hash(self, value: str) -> str:
        """Generate SHA256 hash of memory value"""
        return hashlib.sha256(value.encode()).hexdigest()
    
    def _calculate_age(self, timestamp: str) -> float:
        """Calculate age of memory in seconds"""
        try:
            stored_time = datetime.fromisoformat(timestamp)
            return (datetime.now() - stored_time).total_seconds()
        except:
            return 0.0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored memories"""
        return {
            "total_memories": len(self.memories),
            "total_tags": len(self.memory_index),
            "storage_file": self.storage_file,
            "memory_keys": list(self.memories.keys())
        }


def main():
    """Main function to demonstrate Memory Manager Agent"""
    print("\n=== Memory Manager Agent - TinyFish ===")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize agent
    agent = MemoryManager()
    print("\n[INIT] Memory Manager initialized")
    
    # Demo: Store memories
    print("\n[STORING] Adding sample memories...")
    agent.store_memory("task_1", "Complete ML model training", ["urgent", "ml"])
    agent.store_memory("task_2", "Review code changes", ["code", "review"])
    agent.store_memory("note_1", "Meeting scheduled for 3 PM", ["meeting", "schedule"])
    print(f"Stored 3 memories")
    
    # Demo: Retrieve
    print("\n[RETRIEVING] Fetching specific memory...")
    value = agent.retrieve_memory("task_1")
    print(f"Retrieved: {value}")
    
    # Demo: Search
    print("\n[SEARCHING] Searching for 'code' related memories...")
    results = agent.search_memories(query="code")
    print(f"Found {len(results)} results")
    
    # Demo: Analyze
    print("\n[ANALYZING] Analyzing memory structure...")
    analysis = agent.analyze_memory("task_1")
    print(f"Analysis: {json.dumps(analysis, indent=2, default=str)}")
    
    # Demo: Statistics
    print("\n[STATS] Memory Manager Statistics...")
    stats = agent.get_statistics()
    print(f"Total Memories: {stats['total_memories']}")
    print(f"Total Tags: {stats['total_tags']}")
    
    print("\n=== Memory Manager Agent Execution Complete ===")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
