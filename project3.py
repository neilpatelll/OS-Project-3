#!/usr/bin/env python3
import sys
import os
import struct
from collections import OrderedDict

def write_u64_big_endian(value: int) -> bytes:
    return value.to_bytes(8, 'big', signed=False)

def read_u64_big_endian(buf: bytes, offset: int) -> int:
    return int.from_bytes(buf[offset:offset+8], 'big', signed=False)

BLOCK_SIZE       = 512
MAGIC_HEADER     = b"4348PRJ3"
T               = 10        # Minimum degree
MAX_KEYS        = 2 * T - 1 # = 19
MAX_CHILDREN    = 2 * T     # = 20

HEADER_OFFSET_MAGIC     = 0
HEADER_OFFSET_ROOT      = 8
HEADER_OFFSET_NEXT_BLOCK= 16

# Offsets within a node block:
NODE_OFFSET_BLOCK_ID    = 0
NODE_OFFSET_PARENT      = 8
NODE_OFFSET_NUM_KEYS    = 16
NODE_OFFSET_KEYS        = 24
NODE_OFFSET_VALUES      = NODE_OFFSET_KEYS + (MAX_KEYS * 8)    # 24+152=176
NODE_OFFSET_CHILDREN    = NODE_OFFSET_VALUES + (MAX_KEYS * 8)  # 176+152=328
# 328..488 is child pointers, then remainder is unused


class Node:
    __slots__ = ("block_id", "parent_id", "keys", "values", "children", "dirty")

    def __init__(self, block_id=0):
        self.block_id  = block_id
        self.parent_id = 0
        self.keys      = []
        self.values    = []
        self.children  = []
        self.dirty     = False

    @property
    def num_keys(self):
        return len(self.keys)

    def is_leaf(self):
        return all(c == 0 for c in self.children)

class NodeCache:
    def __init__(self, index_file):
        self.index_file = index_file
        self.cache = OrderedDict()  # block_id -> Node
        self.max_size = 3

    def _evict_if_needed(self):
        while len(self.cache) > self.max_size:
            block_id, node = self.cache.popitem(last=False)
            if node.dirty:
                write_node(self.index_file, node)

    def get_node(self, block_id) -> Node:
        if block_id in self.cache:
            node = self.cache.pop(block_id)
            self.cache[block_id] = node
            return node
        node = read_node(self.index_file, block_id)
        self.cache[block_id] = node
        self._evict_if_needed()
        return node

    def put_node(self, node: Node):
        bid = node.block_id
        if bid in self.cache:
            self.cache.pop(bid)
        self.cache[bid] = node
        self._evict_if_needed()

    def flush_all(self):
        for block_id, node in self.cache.items():
            if node.dirty:
                write_node(self.index_file, node)
        self.cache.clear()

def read_node(index_file, block_id: int) -> Node:
    with open(index_file, "rb") as f:
        f.seek(block_id * BLOCK_SIZE)
        data = f.read(BLOCK_SIZE)

    if len(data) < BLOCK_SIZE:
        raise ValueError(f"Block {block_id} read failed (not 512 bytes).")

    node = Node(block_id)
    node.block_id  = read_u64_big_endian(data, NODE_OFFSET_BLOCK_ID)
    node.parent_id = read_u64_big_endian(data, NODE_OFFSET_PARENT)
    num_keys       = read_u64_big_endian(data, NODE_OFFSET_NUM_KEYS)

    pos = NODE_OFFSET_KEYS
    keys = []
    for _ in range(MAX_KEYS):
        k = read_u64_big_endian(data, pos)
        pos += 8
        keys.append(k)

    values = []
    for _ in range(MAX_KEYS):
        v = read_u64_big_endian(data, pos)
        pos += 8
        values.append(v)

    children = []
    for _ in range(MAX_CHILDREN):
        c = read_u64_big_endian(data, pos)
        pos += 8
        children.append(c)

    node.keys      = keys[:num_keys]
    node.values    = values[:num_keys]
    node.children  = children[:num_keys+1]

    node.dirty = False
    return node

def write_node(index_file, node: Node):
    data = bytearray(BLOCK_SIZE)
    data[NODE_OFFSET_BLOCK_ID: NODE_OFFSET_BLOCK_ID+8]   = write_u64_big_endian(node.block_id)
    data[NODE_OFFSET_PARENT: NODE_OFFSET_PARENT+8]       = write_u64_big_endian(node.parent_id)
    data[NODE_OFFSET_NUM_KEYS: NODE_OFFSET_NUM_KEYS+8]   = write_u64_big_endian(node.num_keys)

    pos = NODE_OFFSET_KEYS
    # up to 19 keys
    for i in range(MAX_KEYS):
        val = node.keys[i] if i < node.num_keys else 0
        data[pos:pos+8] = write_u64_big_endian(val)
        pos += 8

    # up to 19 values
    for i in range(MAX_KEYS):
        val = node.values[i] if i < node.num_keys else 0
        data[pos:pos+8] = write_u64_big_endian(val)
        pos += 8

    # up to 20 children
    for i in range(MAX_CHILDREN):
        val = node.children[i] if i < len(node.children) else 0
        data[pos:pos+8] = write_u64_big_endian(val)
        pos += 8

    with open(index_file, "r+b") as f:
        f.seek(node.block_id * BLOCK_SIZE)
        f.write(data)

    node.dirty = False


def init_header(index_file):
    header = bytearray(BLOCK_SIZE)
    header[0:8]   = MAGIC_HEADER
    # root = 0, next block = 1
    header[8:16]  = write_u64_big_endian(0)
    header[16:24] = write_u64_big_endian(1)
    with open(index_file, "wb") as f:
        f.write(header)

def read_header(index_file):
    if not os.path.exists(index_file):
        raise ValueError("File does not exist.")
    with open(index_file, "rb") as f:
        data = f.read(BLOCK_SIZE)
    if len(data) < BLOCK_SIZE:
        raise ValueError("File too small.")
    if data[0:8] != MAGIC_HEADER:
        raise ValueError("Magic header mismatch. Not a valid index file.")
    root = read_u64_big_endian(data, HEADER_OFFSET_ROOT)
    nxt  = read_u64_big_endian(data, HEADER_OFFSET_NEXT_BLOCK)
    return (root, nxt)

def write_header(index_file, root, nxt):
    with open(index_file, "r+b") as f:
        f.seek(0)
        data = bytearray(f.read(BLOCK_SIZE))
    data[8:16]   = write_u64_big_endian(root)
    data[16:24]  = write_u64_big_endian(nxt)
    with open(index_file, "r+b") as f:
        f.seek(0)
        f.write(data)

def main():
    print("B-tree index file utility - core structure implementation")
    print("Use this program to create, modify, and search B-tree index files.")

if __name__ == "__main__":
    main()