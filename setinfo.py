"""Routines that examine the internals of a CPython set."""

from ctypes import Structure, c_ulong, POINTER, cast, py_object
from math import log

UMAX = 2 ** 32

def cbin(n):
    """Return `n` as a clean 32-bit binary number, without a leading '0b'."""
    if n < 0:
        n = UMAX + n
    return '{0:0>32}'.format(bin(n)[2:])

# Create a singleton with which the set routines below can represent null C
# pointers.

class NULL(object):
    def __repr__(self):
        return 'NULL'

    def __nonzero__(self):
        return False

NULL = NULL()

# Create Structures representing the set object and entries, and
# give them useful methods making them easier to use.


class setentry(Structure):
    """An entry in a set."""
    _fields_ = [
        ('hash', c_ulong),
        ('key', py_object)
        ]

    def __str__(self):
        try:
            return 'setentry({self.hash}, {self.key})'.format(self=self) if self else 'NULL'
        except ValueError:
            return 'NULL'

    def __repr__(self):
        return self.__str__()

class PySetObject(Structure):
    """A set object."""
    _fields_ = [
        ('ob_refcnt', c_ulong),
        ('ob_type', c_ulong),
        ('fill', c_ulong),
        ('used', c_ulong),
        ('mask', c_ulong),
        ('table', POINTER(setentry)),
        ]

    def __len__(self):
        """Return the number of set entry slots."""
        return self.mask + 1

    def slot_of(self, key):
        """Find and return the slot at which `key` is stored."""
        for i in range(len(self)):
            try:
                k = self.table[i].key
            except ValueError:
                continue  # key is NULL
            if (k is key) or (k == key):
                return i
        raise KeyError('cannot find key %r' % (key,))

    def slot_map(self):
        """Return a mapping of keys to their integer slot numbers."""
        m = {}
        for i in range(len(self)):
            entry = self.table[i]
            try:
                entry.key
            except:
                continue  # key is NULL
            m[i] = entry.key
        return m

def setobject(s):
    """Return the PySetObject lying behind the Python set `s`."""
    if not isinstance(s, set):
        raise TypeError('cannot create a setobject from %r' % (s,))
    return cast(id(s), POINTER(PySetObject)).contents

# Retrieve the secret dummy object (it is a simple string, in current versions
# of Python) used internally by sets to represent a previously occupied slot.

dummy = None
s = {0}
s.remove(0)
dummy = setobject(s).table[0].key
del s

def _probe_steps(dummyset, key, final_slot):
    """Find the slots searched to put `key` in `final_slot` of `dummyset`.

    The `dummyset` should be a set in which `key` once resided in position
    `final_slot`, but whose entries have all been deleted, leaving dummy
    entries. This routine will repeatedly try to insert `key` into the set, and
    each time that it does not land at `final_slot` an obstacle is placed where
    it has landed instead, until finally the obstacles make `key` land in the
    `final_slot`.

    A list of the slots searched is returned. The last element of this list will
    always be `final_slot`.
    """
    o = setobject(dummyset)

    # Compute the first slot rather than do an expensive search.
    slot = hash(key) & o.mask
    slots = [ int(slot) ]   # since slot often arrives as a long

    # Keep adding obstacles until `key` winds up in `final_slot`.
    while slots[-1] != final_slot:
        if slot == key:  # make sure the integer `slot` is not `key` itself
            slot += len(o)
        o.table[slot] = setentry(hash(key), None)
        #dummyset[slot] = None  # add the obstacle

        #dummyset[key] = None  # add the key
        dummyset.add(key)
        slot = o.slot_of(key)
        slots.append(slot)
        dummyset.remove(key)

    # Return the sequence of slots that we searched.
    return slots

def probe_steps(keys, key):
    """Return the search sequence for `key` for a set built with `keys`.

    `keys` - Set keys, in order of their insertion, including `key`.
    `key` - The key whose collision path we want to explore.
    """
    # Create a set with the given `keys` and figure out at which
    # slot the target `key` wound up.
    s = set(keys)
    o = setobject(s)
    final_slot = o.slot_of(key)

    # Empty the set so that it contains only dummy entries, then
    # pass it to the internal _probe_steps() routine.
    for k in list(s):
        s.remove(k)
    return _probe_steps(s, key, final_slot)

def probe_all_steps(keys):
    """Return the search sequence for each key in a set built with `keys`.

    `keys` - Set keys, in order of their insertion, including `key`.

    The return value looks like ``{key: [slot, slot, slot], ...}``.

    """
    # Create a set with the given `keys` and find out in which
    # slot each key wound up.
    d = set.fromkeys(keys)
    o = setobject(d)
    m = o.slot_map()

    # For each key in the set, find its probe list.
    for key, final_slot in m.items():
        for k in list(d):
            del d[k]  # empty the set
        m[key] = _probe_steps(d, key, final_slot)
    return m

def display_set(d):
    """Print a set hash table to the screen."""
    do = setobject(d)
    bits = int(log(do.ma_mask + 1, 2))
    for i in range(len(do)):
        entry = do.ma_table[i]
        entry_bits = cbin(i)[-bits:]
        try:
            key = entry.me_key
        except ValueError:  # me_key is NULL
            print('   ' + entry_bits, 'empty')
            continue

        hash_bits = cbin(entry.me_hash)[-bits:]
        if hash_bits == entry_bits:
            print('...' + entry_bits, end=' ')
        else:
            print('***' + hash_bits, end=' ')
        print('[%r] =' % (entry.me_key), end=' ')
        if entry.me_value:
            print('%r' % entry.me_value)
        else:
            print()
