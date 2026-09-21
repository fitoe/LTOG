/* Exercise the actual patched DLL with in-memory labels, no tape device. */
#include "libltfs/ltfs.h"
#include "libltfs/xattr.h"
#include "libltfs/ltog_attributes.h"
#include "ltfs_fuse.h"
#include "libltfs/ltfs_fsops.h"
#include "libltfs/arch/errormap.h"
#include "ltog_attribute_query.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    struct dentry root = {0}, child = {0};
    struct ltfs_index index = {0};
    struct ltfs_label label = {0};
    struct ltfs_volume volume = {0};
    struct ltog_attribute_response response;
    struct extent_info extent = {0};
    char names[3072] = {0};
    char buffer[4096];
    size_t used = 0, i;
    for (i = 0; i < LTOG_ATTRIBUTE_COUNT; ++i) {
        assert(strcmp(ltog_attributes[i].name, "ltfs.driveCaptureDump"));
        assert(strcmp(ltog_attributes[i].name, "ltfs.sync"));
        if (ltog_attributes[i].ea) {
            assert(strcmp(ltog_attributes[i].name, "ltfs.mediaLoads"));
            size_t length = strlen(ltog_attributes[i].name) + 1;
            memcpy(names + used, ltog_attributes[i].name, length);
            used += length;
        }
    }
    int n;
    /* Invalid direction, length, unknown command and flags must be rejected
     * before dereferencing the deliberately absent device or modifying output. */
    memset(&response, 0x5a, sizeof(response));
    assert(ltog_query_attribute(&volume, "/", FSP_FUSE_IOCTL(0xfff, 0, 4096), 0, &response) == -ENOTTY);
    assert(ltog_query_attribute(&volume, "/", FSP_FUSE_IOCTL(0x800, 4096, 4096), 0, &response) == -ENOTTY);
    assert(ltog_query_attribute(&volume, "/", FSP_FUSE_IOCTL(0x800, 0, 32), 0, &response) == -ENOTTY);
    assert(ltog_query_attribute(&volume, "/", FSP_FUSE_IOCTL(0x800, 0, 4096), 1, &response) == -EINVAL);
    assert(response.magic == 0x5a5a5a5a);
    assert(ltfs_init(LTFS_ERR, false, false) == 0);
    assert(init_mrsw(&root.meta_lock) == 0);
    assert(init_mrsw(&child.meta_lock) == 0);
    assert(init_mrsw(&child.contents_lock) == 0);
    TAILQ_INIT(&root.xattrlist);
    TAILQ_INIT(&child.xattrlist);
    TAILQ_INIT(&child.extentlist);
    index.root = &root;
    volume.index = &index;
    volume.label = &label;
    strcpy(label.barcode, "ID0001");
    strcpy(label.vol_uuid, "11111111-2222-4333-8444-555555555555");

    n = xattr_list(&root, NULL, 0, &volume);
    assert(n == used && used < 3072);
    memset(buffer, 0x5a, sizeof(buffer));
    assert(xattr_list(&root, buffer, n - 1, &volume) == -LTFS_SMALL_BUFFER);
    assert(buffer[n - 1] == 0x5a); /* no write past the advertised size */
    assert(xattr_list(&root, buffer, n, &volume) == n);
    assert(memcmp(buffer, names, n) == 0);
    assert(buffer[n] == 0x5a);
    assert(xattr_list(&child, NULL, 0, &volume) == 0);
    extent.start.partition = 'b';
    extent.start.block = 12345;
    TAILQ_INSERT_TAIL(&child.extentlist, &extent, list);
    assert(xattr_get(&child, "ltfs.partition", buffer, sizeof(buffer), &volume) == 1);
    assert(buffer[0] == 'b');
    assert(xattr_get(&child, "ltfs.startblock", buffer, sizeof(buffer), &volume) == 5);
    assert(memcmp(buffer, "12345", 5) == 0);
    TAILQ_REMOVE(&child.extentlist, &extent, list);

    assert(xattr_get(&root, "ltfs.volumeSerial", buffer, sizeof(buffer), &volume) == 6);
    assert(memcmp(buffer, "ID0001", 6) == 0);
    assert(xattr_get(&root, "ltfs.volumeUUID", buffer, sizeof(buffer), &volume) == 36);
    assert(memcmp(buffer, label.vol_uuid, 36) == 0);
    /* These setters must reject before touching any device or dirty index. */
    assert(xattr_set(&root, "ltfs.volumeSerial", "BAD001", 6, 0, &volume) == -LTFS_RDONLY_XATTR);
    assert(xattr_set(&root, "ltfs.volumeUUID", "bad", 3, 0, &volume) == -LTFS_RDONLY_XATTR);
    assert(strcmp(label.barcode, "ID0001") == 0);
    strcpy(label.barcode, "ID0002");
    assert(xattr_get(&root, "ltfs.volumeSerial", buffer, sizeof(buffer), &volume) == 6);
    assert(memcmp(buffer, "ID0002", 6) == 0); /* no getter cache */
    label.barcode[0] = 0;
    assert(xattr_get(&root, "ltfs.volumeSerial", buffer, sizeof(buffer), &volume) == 0);
    destroy_mrsw(&child.meta_lock);
    destroy_mrsw(&child.contents_lock);
    destroy_mrsw(&root.meta_lock);
    puts("PASS: root metadata enumeration, exact/short buffers, live getters, file positions, missing serial, write and invalid IOCTL rejection");
    return 0;
}
