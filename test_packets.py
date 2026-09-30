"""Offline tests: packet shapes and patch logic (no device needed)."""
import importlib.util
spec = importlib.util.spec_from_file_location('f35c', 'f35c.py')
f35c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f35c)

# page templates: 33 bytes, right structure
for name in ('PAGE00', 'PAGE18', 'PAGE30', 'PAGE48'):
    b = bytes.fromhex(getattr(f35c, name))
    assert len(b) == 33, name
    assert b[0] == 0x04 and b[3] == 0x06, name

# light template + ritual
assert len(bytes.fromhex(f35c.LIGHT_PKT)) == 33
assert len(bytes.fromhex(f35c.LIGHT_COMMIT)) == 32

# le16 encoding
assert f35c.le16pair(800) == '2003' * 2
assert f35c.le16pair(1600) == '4006' * 2

# stage patching
d = f35c.F35C.__new__(f35c.F35C)
d.pages = dict(PAGE00=f35c.PAGE00, PAGE18=f35c.PAGE18,
               PAGE30=f35c.PAGE30, PAGE48=f35c.PAGE48)
d._patch('PAGE18', f35c.STAGE_SLOT[3][1], 8, f35c.le16pair(1100))
p = bytes.fromhex(d.pages['PAGE18'])
assert p[18:22] == bytes.fromhex('4c044c04')
assert p[2] == 0x04, 'changed-page flag'
print('all packet tests OK')
