/*
 * Test fixture for function pointer tracking
 * Tests:
 * - Direct function pointer assignment
 * - Address-of function pointer assignment
 * - Struct member function pointer
 * - Array function pointer
 * - Typedef function pointer
 */

typedef void (*callback_t)(int);
typedef int (*handler_func)(void*, size_t);

/* Callback table */
callback_t callback_table[10];

/* Struct with function pointer */
struct handler_ops {
    handler_func process;
    handler_func cleanup;
};

/* Target functions */
void my_callback(int val) {
    printf("Callback called with %d\n", val);
}

int process_data(void* data, size_t len) {
    if (data == NULL || len == 0) {
        return -1;
    }
    return 0;
}

int cleanup_handler(void* data, size_t len) {
    if (data) {
        free(data);
    }
    return 0;
}

/* Test: Direct pointer assignment */
void test_direct_assignment(void) {
    callback_t cb = my_callback;
    cb(42);
}

/* Test: Address-of assignment */
void test_addressof_assignment(void) {
    callback_t cb = &my_callback;
    cb(100);
}

/* Test: Struct member assignment */
void test_struct_member(void) {
    struct handler_ops ops;
    ops.process = process_data;
    ops.cleanup = cleanup_handler;
    
    ops.process(NULL, 0);
    ops.cleanup(NULL, 0);
}

/* Test: Array assignment */
void test_array_funcptr(void) {
    callback_table[0] = my_callback;
    callback_table[1] = my_callback;
    
    for (int i = 0; i < 2; i++) {
        callback_table[i](i);
    }
}

/* Test: Callback registration pattern */
void register_callback(callback_t cb) {
    static callback_t saved_cb = NULL;
    saved_cb = cb;
}

void setup_callbacks(void) {
    register_callback(my_callback);
}
