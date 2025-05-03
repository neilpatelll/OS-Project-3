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

def btree_search_key(cache: NodeCache, root_id: int, search_key: int):
    if root_id == 0:
        return None
    node = cache.get_node(root_id)
    i = 0
    while i < node.num_keys and search_key > node.keys[i]:
        i += 1
    if i < node.num_keys and node.keys[i] == search_key:
        return (node.keys[i], node.values[i])
    if i < len(node.children) and node.children[i] != 0:
        return btree_search_key(cache, node.children[i], search_key)
    return None

def btree_insert(cache: NodeCache, index_file: str, root_id: int, key: int, value: int):
    if root_id == 0:
        # create root
        root_id = allocate_new_node(index_file)
        root_node = cache.get_node(root_id)
        root_node.keys     = [key]
        root_node.values   = [value]
        root_node.children = []
        root_node.parent_id= 0
        root_node.dirty    = True
        cache.put_node(root_node)
        return root_id

    root_node = cache.get_node(root_id)
    if root_node.num_keys == MAX_KEYS:
        # split root
        new_root_id = allocate_new_node(index_file)
        new_root_node = cache.get_node(new_root_id)
        new_root_node.keys     = []
        new_root_node.values   = []
        new_root_node.children = [root_id]
        new_root_node.parent_id= 0
        new_root_node.dirty    = True
        root_node.parent_id    = new_root_id
        root_node.dirty        = True
        cache.put_node(root_node)

        split_child(cache, index_file, new_root_node, 0)
        insert_non_full(cache, index_file, new_root_node, key, value)
        return new_root_id
    else:
        insert_non_full(cache, index_file, root_node, key, value)
        return root_id

def insert_non_full(cache: NodeCache, index_file: str, node: Node, key: int, value: int):
    i = node.num_keys - 1
    if node.is_leaf():
        node.keys.append(0)
        node.values.append(0)
        while i >= 0 and key < node.keys[i]:
            node.keys[i+1]   = node.keys[i]
            node.values[i+1] = node.values[i]
            i -= 1
        node.keys[i+1]   = key
        node.values[i+1] = value
        node.dirty       = True
        cache.put_node(node)
    else:
        while i >= 0 and key < node.keys[i]:
            i -= 1
        i += 1
        child_id = node.children[i]
        child = cache.get_node(child_id)
        if child.num_keys == MAX_KEYS:
            split_child(cache, index_file, node, i)
            if key > node.keys[i]:
                i += 1
        child_id = node.children[i]
        child = cache.get_node(child_id)
        insert_non_full(cache, index_file, child, key, value)

def split_child(cache: NodeCache, index_file: str, parent: Node, child_index: int):
    """
    Splits the parent's child at child_index (which is assumed full),
    creating a new node for the top half. Moves the median key up into parent.
    """
    full_child_id = parent.children[child_index]
    full_child = cache.get_node(full_child_id)

    # Copy old arrays so we can safely slice after
    old_keys     = full_child.keys
    old_values   = full_child.values
    old_children = full_child.children

    new_node_id = allocate_new_node(index_file)
    new_node = cache.get_node(new_node_id)
    new_node.parent_id = parent.block_id

    mid = T - 1  # 9 for T=10

    # The median key to move up is old_keys[mid]
    median_key = old_keys[mid]
    median_val = old_values[mid]

    # The new node gets keys from mid+1..end
    new_node.keys   = old_keys[mid+1:]
    new_node.values = old_values[mid+1:]

    if not full_child.is_leaf():
        new_node.children = old_children[mid+1:]
        # fix each child's parent
        for c_id in new_node.children:
            if c_id != 0:
                c_node = cache.get_node(c_id)
                c_node.parent_id = new_node_id
                c_node.dirty = True
                cache.put_node(c_node)
    else:
        new_node.children = []

    # Now shrink the original child to 0..(mid-1)
    full_child.keys   = old_keys[:mid]
    full_child.values = old_values[:mid]
    if not full_child.is_leaf():
        full_child.children = old_children[:mid+1]

    full_child.dirty = True
    new_node.dirty   = True
    cache.put_node(full_child)
    cache.put_node(new_node)

    # Insert the median key in the parent
    parent.keys.insert(child_index, median_key)
    parent.values.insert(child_index, median_val)
    parent.children.insert(child_index+1, new_node_id)

    parent.dirty = True
    cache.put_node(parent)

def allocate_new_node(index_file: str) -> int:
    root, nxt = read_header(index_file)
    block_id = nxt
    nxt += 1
    write_header(index_file, root, nxt)

    # Write a blank node with the correct block_id so it won't be 0 on read
    node = Node(block_id)
    node.dirty = True
    write_node(index_file, node)
    return block_id

def main():
    print("B-tree index file utility - core structure implementation")
    print("Use this program to create, modify, and search B-tree index files.")

if __name__ == "__main__":
    main()