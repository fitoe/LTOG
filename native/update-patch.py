"""Generate/check the native patch from pinned upstream source and the catalog.

Does not edit the extracted build tree. To change an already-applied patch,
reverse the old patch in the build tree before regenerating it.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def generate():
    archive = ROOT / "build/winltfs-source.zip"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != "8fd9d8ba574672fda6e48ab1fc80d97ba4275d39ce3ed03da3b7e0461892c2ff":
        raise RuntimeError("Source checksum mismatch")
    with zipfile.ZipFile(archive) as z:
        def original(path):
            return z.read("WinLtfs-1.1.1/" + path).decode().replace("\r\n", "\n")
        originals = {p: original(p) for p in (
            "ltfs/src/libltfs/xattr.c", "ltfs/src/ltfs_fuse.c", "ltfs/src/main.c")}
    changed = dict(originals)
    catalog = json.loads((ROOT / "tools/ltfs_attributes.json").read_text())
    assert len({r['id'] for r in catalog}) == len(catalog)
    assert len({r['name'].lower() for r in catalog}) == len(catalog)
    assert all(0x800 <= r['id'] <= 0xfff for r in catalog)
    assert not any(r['name'] in ('ltfs.sync', 'ltfs.driveCaptureDump', 'ltfs.volumeLockState')
                   or '.vendor.' in r['name'] for r in catalog)
    header = '''/* Generated from tools/ltfs_attributes.json; LGPL-2.1. Stable command IDs. */
#ifndef LTOG_ATTRIBUTES_H
#define LTOG_ATTRIBUTES_H
struct ltog_attribute { unsigned int id; const char *name; int root; int ea; };
static const struct ltog_attribute ltog_attributes[] = {
'''
    header += ''.join(f'    {{0x{r["id"]:03x}, "{r["name"]}", {int(r["scope"] == "root")}, {int(r["ea"])} }},\n' for r in catalog)
    header += '};\n#define LTOG_ATTRIBUTE_COUNT (sizeof(ltog_attributes) / sizeof(ltog_attributes[0]))\n#endif\n'
    changed['ltfs/src/libltfs/ltog_attributes.h'] = header
    changed['ltfs/src/ltog_attribute_query.h'] = (ROOT / 'native/attribute-query.h').read_text()
    path = 'ltfs/src/libltfs/xattr.c'
    changed[path] = changed[path].replace('#include "xattr.h"', '#include "xattr.h"\n#ifdef mingw_PLATFORM\n#include "ltog_attributes.h"\n#endif')
    anchor = '\tnbytes += ret;\n\n\t/*\n\t * There used to be'
    changed[path] = changed[path].replace(anchor, '''\tnbytes += ret;

#ifdef mingw_PLATFORM
	/* Only cheap, side-effect-free metadata on root EA enumeration. Hardware
	 * diagnostics and file metadata use the output-only query interface. */
	if (d == vol->index->root) {
		size_t i;
		for (i = 0; i < LTOG_ATTRIBUTE_COUNT; ++i) {
			size_t length;
			if (!ltog_attributes[i].ea)
				continue;
			length = strlen(ltog_attributes[i].name) + 1;
			if (size && (size_t)nbytes + length <= size)
				memcpy(list + nbytes, ltog_attributes[i].name, length);
			nbytes += length;
		}
	}
#endif

	/*
	 * There used to be''')
    # Existing encryption getters issue MODE SENSE without a device lock.
    # Serialize with tape I/O, like the capacity and health getters already do.
    for name, getter in [('mediaEncrypted', 'tape_get_media_encrypted'),
                         ('driveEncryptionState', 'tape_get_drive_encryption_state'),
                         ('driveEncryptionMethod', 'tape_get_drive_encryption_method')]:
        old = f'\t\t\tret = _xattr_get_string({getter}(vol->device), &val, name);'
        new = f'''\t\t\tret = tape_device_lock(vol->device);
			if (ret == 0) {{
				ret = _xattr_get_string({getter}(vol->device), &val, name);
				tape_device_unlock(vol->device);
			}}'''
        assert old in changed[path]
        changed[path] = changed[path].replace(old, new)
    path = 'ltfs/src/ltfs_fuse.c'
    anchor = '\tret = ltfs_fsops_listxattr(path, list, size, &id, priv->data);'
    changed[path] = changed[path].replace(anchor, '''#ifdef mingw_PLATFORM
	/* Revalidate the mounted medium before publishing its root metadata. */
	if (!strcmp(path, "/")) {
		ret = ltfs_test_unit_ready(priv->data);
		if (ret < 0)
			return errormap_fuse_error(ret);
	}
#endif

''' + anchor)
    changed[path] = changed[path].replace('struct fuse_operations ltfs_ops = {', '''#ifdef mingw_PLATFORM
#include "ltog_attribute_query.h"
#endif

struct fuse_operations ltfs_ops = {
#ifdef mingw_PLATFORM
	.ioctl       = ltfs_fuse_ioctl,
#endif''')
    path = 'ltfs/src/main.c'
    anchor = '\t/* now we can safely call FUSE */'
    changed[path] = changed[path].replace(anchor, '''#ifdef mingw_PLATFORM
	/* A cached EA must not outlive a media change, even for CLI mounts. */
	ret = fuse_opt_add_arg(args, "-oEaTimeout=0");
	if (ret < 0)
		return 1;
#endif

''' + anchor)
    patch = ''
    for path, content in changed.items():
        patch += ''.join(difflib.unified_diff(originals.get(path, '').splitlines(True),
            content.splitlines(True), fromfile='a/' + path if path in originals else '/dev/null',
            tofile='b/' + path))
    return patch


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    patch = ROOT / 'native/root-identity.patch'
    generated = generate()
    if args.check:
        if patch.read_text() != generated:
            raise SystemExit('Native patch/catalog mismatch: run python native/update-patch.py')
    else:
        patch.write_text(generated, encoding='utf-8', newline='\n')
