/* LGPL-2.1: read-only WinFsp control interface. Included by ltfs_fuse.c.
 * A fixed output-only command per allowlisted attribute; no arbitrary xattr
 * names, setters, tape handles or filesystem mutations are accepted.
 */
#include "libltfs/ltog_attributes.h"

struct ltog_attribute_response {
    uint32_t magic;
    uint32_t version;
    int32_t status;             /* raw LTFS error, or 0 */
    uint32_t length;
    char volume_uuid[40];      /* binds separate replies to one mounted volume */
    char reserved[8];
    char value[4032];          /* UTF-8, length delimited */
};
typedef char ltog_response_size_check[sizeof(struct ltog_attribute_response) == 4096 ? 1 : -1];

static int ltog_query_attribute(struct ltfs_volume *vol, const char *path,
    unsigned int cmd, unsigned int flags, void *data)
{
    const struct ltog_attribute *attribute = NULL;
    struct ltog_attribute_response *response = data;
    ltfs_file_id id;
    int ret;
    size_t i;
    if (flags || !data || !path || !vol)
        return -EINVAL;
    for (i = 0; i < LTOG_ATTRIBUTE_COUNT; ++i) {
        if (cmd == (unsigned int)FSP_FUSE_IOCTL(ltog_attributes[i].id, 0, 4096)) {
            attribute = &ltog_attributes[i];
            break;
        }
    }
    if (!attribute)
        return -ENOTTY;
    memset(response, 0, sizeof(*response));
    response->magic = 0x474f544c; /* LTOG, little endian */
    response->version = 1;
    /* Same device handle as the mount; no tape movement unless the engine
     * needs its normal media-change revalidation. Nothing is synchronized. */
    ret = ltfs_test_unit_ready(vol);
    if (ret < 0)
        return errormap_fuse_error(ret);
    ret = attribute->root && strcmp(path, "/") ? -LTFS_NO_XATTR :
        ltfs_fsops_getxattr(path, attribute->name, response->value,
            sizeof(response->value), &id, vol);
    if (ret >= 0)
        response->length = ret;
    else {
        memset(response->value, 0, sizeof(response->value));
        response->status = ret;
    }
    /* Fail the entire observation after failed media revalidation, rather
     * than presenting earlier values as a valid multi-attribute report. */
    ret = ltfs_test_unit_ready(vol);
    if (ret < 0)
        return errormap_fuse_error(ret);
    ret = ltfs_get_volume_lock(false, vol);
    if (ret < 0)
        return errormap_fuse_error(ret);
    if (vol->label)
        memcpy(response->volume_uuid, vol->label->vol_uuid, 36);
    releaseread_mrsw(&vol->lock);
    return 0;
}

static int ltfs_fuse_ioctl(const char *path, int cmd, void *arg,
    struct fuse_file_info *fi, unsigned int flags, void *data)
{
    struct ltfs_fuse_data *priv = fuse_get_context()->private_data;
    return ltog_query_attribute(priv->data, path, (unsigned int)cmd, flags, data);
}
