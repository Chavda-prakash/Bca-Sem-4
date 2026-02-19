# Memory Manager Agent - TinyFish Implementation

## Overview

A comprehensive **Memory Manager Agent** built for TinyFish platform with persistent storage and advanced analysis capabilities. This agent is designed to manage, store, retrieve, and analyze memories efficiently.

## Features

✅ **Core Features:**
- Store memories with metadata (timestamp, tags, hash)
- Retrieve memories by unique key
- Search memories by query string or tags
- Analyze memory entries for insights
- Delete memories from storage
- List all memories with optional tag filtering
- Persistent JSON-based storage
- SHA256 hash generation for data integrity
- Statistics and reporting

## Installation

```bash
# Clone the repository
git clone https://github.com/Chavda-prakash/Bca-Sem-4.git
cd Bca-Sem-4

# Run the agent
python memory_manager.py
```

## Usage

### Basic Example

```python
from memory_manager import MemoryManager

# Initialize agent
agent = MemoryManager(storage_file="memories.json")

# Store a memory
agent.store_memory("task_1", "Complete project", ["urgent", "work"])

# Retrieve a memory
memory = agent.retrieve_memory("task_1")
print(memory)  # Output: Complete project

# Search memories
results = agent.search_memories(query="project")
print(f"Found {len(results)} results")

# List all memories
all_memories = agent.list_memories()
print(all_memories)

# Get statistics
stats = agent.get_statistics()
print(stats)
```

## API Reference

### Methods

| Method | Description | Returns |
|--------|-------------|----------|
| `store_memory(key, value, tags)` | Store a memory entry | `bool` |
| `retrieve_memory(key)` | Fetch memory by key | `Any` \| `None` |
| `search_memories(query, tag)` | Search for memories | `List[Dict]` |
| `analyze_memory(key)` | Analyze memory structure | `Dict[str, Any]` |
| `delete_memory(key)` | Remove a memory | `bool` |
| `list_memories(tag)` | List all memories | `List[str]` |
| `save_memories()` | Save to persistent storage | `bool` |
| `load_memories()` | Load from persistent storage | `bool` |
| `get_statistics()` | Get memory statistics | `Dict[str, Any]` |

## Storage Format

Memories are stored in JSON format:

```json
{
  "task_1": {
    "value": "Complete ML model training",
    "timestamp": "2026-02-19T14:30:00.123456",
    "tags": ["urgent", "ml"],
    "hash": "a1b2c3d4e5f6..."
  }
}
```

## Use Cases

1. **Task Management** - Store and retrieve tasks with priorities
2. **Knowledge Base** - Maintain searchable memory of information
3. **Agent Learning** - Persistent memory for AI agents
4. **Data Caching** - Quick access to frequently used information
5. **Audit Trail** - Track all stored data with timestamps

## Testing

Run the main function to test all features:

```bash
python memory_manager.py
```

Output will show:
- ✓ Memory initialization
- ✓ Storage of 3 sample memories
- ✓ Retrieval demonstration
- ✓ Search functionality
- ✓ Analysis results
- ✓ Statistics output

## Performance Metrics

- **Storage**: JSON file-based (scalable to thousands of entries)
- **Retrieval**: O(1) average for key-based lookup
- **Search**: O(n) for query-based search
- **Memory Usage**: Minimal - only loaded on demand

## Version

**v1.0.0** - Initial release with core functionality

## Author

**Chavda-prakash** - BCA Semester 4

## License

MIT License - Feel free to use and modify

## Testing with CodeRabbit

This project is integrated with CodeRabbit for continuous code analysis and quality metrics.

- Repository: https://github.com/Chavda-prakash/Bca-Sem-4
- Integration: CodeRabbit AI Code Reviews
- Status: Active monitoring and analysis

## Contributing

Feel free to submit issues and enhancement requests!

---

**Last Updated**: 2026-02-19  
**Status**: ✅ Production Ready
