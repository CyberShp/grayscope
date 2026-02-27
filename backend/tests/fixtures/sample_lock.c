/**
 * Sample C file for testing lock operation extraction.
 * Contains pthread mutex operations and potential deadlock patterns.
 */

#include <pthread.h>
#include <stdio.h>

pthread_mutex_t g_lock_a;
pthread_mutex_t g_lock_b;
int g_shared_data = 0;
int g_counter = 0;

/* Thread-safe increment (well-behaved) */
void safe_increment(void) {
    pthread_mutex_lock(&g_lock_a);
    g_shared_data++;
    pthread_mutex_unlock(&g_lock_a);
}

/* Potential lock leak in error path */
int risky_operation(int *result) {
    pthread_mutex_lock(&g_lock_a);
    
    if (result == NULL) {
        // Bug: lock not released on error path
        return -1;
    }
    
    *result = g_shared_data;
    g_counter++;
    pthread_mutex_unlock(&g_lock_a);
    return 0;
}

/* ABBA deadlock pattern - path 1 */
void path_a_handler(void) {
    pthread_mutex_lock(&g_lock_a);
    g_shared_data = 1;
    pthread_mutex_lock(&g_lock_b);
    g_counter++;
    pthread_mutex_unlock(&g_lock_b);
    pthread_mutex_unlock(&g_lock_a);
}

/* ABBA deadlock pattern - path 2 (reverse order) */
void path_b_handler(void) {
    pthread_mutex_lock(&g_lock_b);
    g_counter = 1;
    pthread_mutex_lock(&g_lock_a);
    g_shared_data++;
    pthread_mutex_unlock(&g_lock_a);
    pthread_mutex_unlock(&g_lock_b);
}

/* Branch-dependent locking */
void conditional_lock(int condition) {
    if (condition > 0) {
        pthread_mutex_lock(&g_lock_a);
        g_shared_data++;
        // Bug: unlock only in this branch
    } else {
        g_counter++;
    }
    // g_lock_a may or may not be held here
    pthread_mutex_unlock(&g_lock_a);
}

/* Entry callback */
void on_message_callback(int type, void *data) {
    if (type == 1) {
        safe_increment();
    } else if (type == 2) {
        path_a_handler();
    }
}

void *thread_entry(void *arg) {
    on_message_callback(1, arg);
    return NULL;
}
