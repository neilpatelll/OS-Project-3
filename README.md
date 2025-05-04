# CS4348 Project 3: B-Tree Index File Manager

## Project Overview

This program implements an interactive command-line utility for creating and managing index files containing B-trees. Users can create index files, insert key-value pairs, search for specific keys, load data from CSV files, print all key-value pairs, and extract data to CSV files.

## Implementation Details

- **Language Used**: Python
- **B-Tree Configuration**: Minimal degree of 10 (19 key/value pairs, 20 child pointers per node)
- **Memory Management**: Never more than 3 nodes in memory at a time (implemented with LRU cache)
- **Block Size**: Fixed 512 bytes per node
- **Integer Format**: 8-byte integers with big-endian byte order

## File Structure

### Header Block (512 bytes)
- 8 bytes: Magic number "4348PRJ3" (ASCII values)
- 8 bytes: Root node block ID (0 if tree is empty)
- 8 bytes: Next available block ID
- Remaining bytes: Unused

### Node Block (512 bytes)
- 8 bytes: Block ID of this node
- 8 bytes: Parent node block ID (0 if root)
- 8 bytes: Number of key/value pairs in this node
- 152 bytes: Array of 19 keys (64-bit each)
- 152 bytes: Array of 19 values (64-bit each)
- 160 bytes: Array of 20 child pointers (64-bit block IDs, 0 if leaf)
- Remaining bytes: Unused

## Commands

The program accepts the following commands as command-line arguments:

### create
Creates a new index file.
```
python project3.py create <index_file>
```
Example: `python project3.py create test.idx`

### insert
Inserts a key-value pair into the index.
```
python project3.py insert <index_file> <key> <value>
```
Example: `python project3.py insert test.idx 15 100`

### search
Searches for a key in the index.
```
python project3.py search <index_file> <key>
```
Example: `python project3.py search test.idx 15`

### load
Loads key-value pairs from a CSV file.
```
python project3.py load <index_file> <csv_file>
```
Example: `python project3.py load test.idx input.csv`

### print
Prints all key-value pairs in the index.
```
python project3.py print <index_file>
```
Example: `python project3.py print test.idx`

### extract
Saves all key-value pairs to a CSV file.
```
python project3.py extract <index_file> <output_file>
```
Example: `python project3.py extract test.idx output.csv`

## Implementation Features

- **LRU Cache**: Ensures no more than 3 nodes are in memory at any time
- **Error Handling**: Comprehensive error checking for invalid files, commands, and inputs
- **Balanced Structure**: B-tree maintains balance on insertions
- **Binary I/O**: Efficient serialization using big-endian byte order
- **Node Splitting**: Correctly implements node splitting when nodes become full

## Development Notes

The implementation follows standard B-tree algorithms with special attention to:
1. Memory constraints (max 3 nodes in memory)
2. Proper disk I/O with binary serialization
3. Node splitting and tree restructuring
4. Command-line argument parsing and validation

## Usage Examples

### Creating a new index file:
```
python project3.py create myindex.idx
```

### Inserting values:
```
python project3.py insert myindex.idx 42 100
python project3.py insert myindex.idx 23 200
```

### Searching for a key:
```
python project3.py search myindex.idx 42
```
Output: `Key: 42, Value: 100`

### Loading from CSV:
```
python project3.py load myindex.idx data.csv
```

### Printing all entries:
```
python project3.py print myindex.idx
```

### Extracting to CSV:
```
python project3.py extract myindex.idx output.csv
```
