/**
 * Simulated distributed storage module for GrayScope analysis testing.
 * Contains typical patterns: error handling, resource management,
 * boundary conditions, and call graph complexity.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>

#define MAX_BLOCK_SIZE  (4 * 1024 * 1024)  /* 4 MiB */
#define MAX_KEY_LEN     256
#define MAX_RETRIES     3
#define POOL_SIZE       64

/* ---- data structures ---- */

typedef struct {
    char key[MAX_KEY_LEN];
    void *data;
    size_t size;
    int ref_count;
    pthread_mutex_t lock;
} block_entry_t;

typedef struct {
    block_entry_t *entries[POOL_SIZE];
    int count;
    pthread_mutex_t pool_lock;
} block_pool_t;

/* ---- forward declarations ---- */

static int validate_key(const char *key);
static int validate_size(size_t size);
static block_entry_t *alloc_entry(const char *key, size_t size);
static void free_entry(block_entry_t *entry);
static int pool_insert(block_pool_t *pool, block_entry_t *entry);
static block_entry_t *pool_lookup(block_pool_t *pool, const char *key);

/* ---- implementation ---- */

/**
 * Validate a storage key.
 * Missing check: key could be exactly MAX_KEY_LEN (off-by-one).
 */
static int validate_key(const char *key) {
    if (key == NULL) {
        return -EINVAL;
    }
    size_t len = strlen(key);
    if (len == 0) {
        return -EINVAL;
    }
    if (len >= MAX_KEY_LEN) {
        return -ENAMETOOLONG;
    }
    return 0;
}

/**
 * Validate block size with boundary conditions.
 */
static int validate_size(size_t size) {
    if (size == 0) {
        return -EINVAL;
    }
    if (size > MAX_BLOCK_SIZE) {
        return -EFBIG;
    }
    return 0;
}

/**
 * Allocate a new block entry.
 * Bug: missing free(entry) on malloc failure for data.
 */
static block_entry_t *alloc_entry(const char *key, size_t size) {
    block_entry_t *entry = malloc(sizeof(block_entry_t));
    if (entry == NULL) {
        return NULL;
    }

    entry->data = malloc(size);
    if (entry->data == NULL) {
        /* BUG: forgot to free(entry) here! */
        return NULL;
    }

    strncpy(entry->key, key, MAX_KEY_LEN - 1);
    entry->key[MAX_KEY_LEN - 1] = '\0';
    entry->size = size;
    entry->ref_count = 1;
    pthread_mutex_init(&entry->lock, NULL);

    return entry;
}

/**
 * Free a block entry and its resources.
 */
static void free_entry(block_entry_t *entry) {
    if (entry == NULL) {
        return;
    }
    if (entry->data != NULL) {
        free(entry->data);
        entry->data = NULL;
    }
    pthread_mutex_destroy(&entry->lock);
    free(entry);
}

/**
 * Insert entry into pool with lock.
 * Bug: pool_lock not released on ENOSPC error path.
 */
static int pool_insert(block_pool_t *pool, block_entry_t *entry) {
    if (pool == NULL || entry == NULL) {
        return -EINVAL;
    }

    pthread_mutex_lock(&pool->pool_lock);

    if (pool->count >= POOL_SIZE) {
        /* BUG: forgot pthread_mutex_unlock here! */
        return -ENOSPC;
    }

    /* Check for duplicate key */
    for (int i = 0; i < pool->count; i++) {
        if (strcmp(pool->entries[i]->key, entry->key) == 0) {
            pthread_mutex_unlock(&pool->pool_lock);
            return -EEXIST;
        }
    }

    pool->entries[pool->count] = entry;
    pool->count++;

    pthread_mutex_unlock(&pool->pool_lock);
    return 0;
}

/**
 * Lookup entry by key.
 */
static block_entry_t *pool_lookup(block_pool_t *pool, const char *key) {
    if (pool == NULL || key == NULL) {
        return NULL;
    }

    pthread_mutex_lock(&pool->pool_lock);

    for (int i = 0; i < pool->count; i++) {
        if (strcmp(pool->entries[i]->key, key) == 0) {
            block_entry_t *found = pool->entries[i];
            pthread_mutex_unlock(&pool->pool_lock);
            return found;
        }
    }

    pthread_mutex_unlock(&pool->pool_lock);
    return NULL;
}

/**
 * Write data to storage with full validation and retry.
 * This is the main API entry point demonstrating complex error handling.
 */
int storage_write(block_pool_t *pool, const char *key,
                  const void *data, size_t size) {
    int ret;
    int retries = 0;

    /* validate inputs */
    ret = validate_key(key);
    if (ret < 0) {
        return ret;
    }

    ret = validate_size(size);
    if (ret < 0) {
        return ret;
    }

    /* allocate entry */
    block_entry_t *entry = alloc_entry(key, size);
    if (entry == NULL) {
        return -ENOMEM;
    }

    /* copy data */
    memcpy(entry->data, data, size);

    /* insert with retry */
    while (retries < MAX_RETRIES) {
        ret = pool_insert(pool, entry);
        if (ret == 0) {
            return 0;
        }
        if (ret == -EEXIST) {
            free_entry(entry);
            return -EEXIST;
        }
        retries++;
    }

    /* all retries exhausted */
    free_entry(entry);
    return -EIO;
}

/**
 * Read data from storage.
 */
int storage_read(block_pool_t *pool, const char *key,
                 void *buf, size_t buf_size, size_t *out_size) {
    int ret;

    ret = validate_key(key);
    if (ret < 0) {
        return ret;
    }

    block_entry_t *entry = pool_lookup(pool, key);
    if (entry == NULL) {
        return -ENOENT;
    }

    pthread_mutex_lock(&entry->lock);

    if (buf_size < entry->size) {
        pthread_mutex_unlock(&entry->lock);
        return -ERANGE;
    }

    memcpy(buf, entry->data, entry->size);
    if (out_size != NULL) {
        *out_size = entry->size;
    }

    pthread_mutex_unlock(&entry->lock);
    return 0;
}

/**
 * Delete entry from pool.
 * Bug: race condition - entry could be freed while still referenced.
 */
int storage_delete(block_pool_t *pool, const char *key) {
    int ret;

    ret = validate_key(key);
    if (ret < 0) {
        return ret;
    }

    pthread_mutex_lock(&pool->pool_lock);

    for (int i = 0; i < pool->count; i++) {
        if (strcmp(pool->entries[i]->key, key) == 0) {
            block_entry_t *entry = pool->entries[i];

            /* shift remaining entries */
            for (int j = i; j < pool->count - 1; j++) {
                pool->entries[j] = pool->entries[j + 1];
            }
            pool->count--;

            pthread_mutex_unlock(&pool->pool_lock);

            /* BUG: no ref_count check before freeing! */
            free_entry(entry);
            return 0;
        }
    }

    pthread_mutex_unlock(&pool->pool_lock);
    return -ENOENT;
}

/**
 * Batch write multiple keys. High fan-out function.
 */
int storage_batch_write(block_pool_t *pool, const char **keys,
                        const void **data, const size_t *sizes,
                        int count) {
    if (count <= 0 || count > POOL_SIZE) {
        return -EINVAL;
    }

    int success = 0;
    int last_err = 0;

    for (int i = 0; i < count; i++) {
        int ret = storage_write(pool, keys[i], data[i], sizes[i]);
        if (ret == 0) {
            success++;
        } else {
            last_err = ret;
        }
    }

    if (success == count) {
        return 0;
    }
    if (success == 0) {
        return last_err;
    }
    return -EIO;  /* partial success */
}
