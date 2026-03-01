/*
 * Test fixture for security vulnerability detection
 * Tests:
 * - Integer overflow in malloc
 * - Buffer overflow with unsafe string functions
 * - Format string vulnerabilities
 * - TOCTOU race conditions
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <fcntl.h>

/* ========== Integer Overflow Tests ========== */

/* Test: Integer overflow in malloc - VULNERABLE */
void* allocate_buffer(size_t count, size_t size) {
    /* No overflow check before multiplication */
    void* buf = malloc(count * size);
    return buf;
}

/* Test: Integer overflow with range check - SAFE */
void* allocate_buffer_safe(size_t count, size_t size) {
    if (count > SIZE_MAX / size) {
        return NULL;
    }
    void* buf = malloc(count * size);
    return buf;
}

/* Test: Array index overflow - VULNERABLE */
void copy_data(int* dest, int* src, size_t num_elements) {
    size_t total_size = num_elements * sizeof(int);
    memcpy(dest, src, total_size);
}

/* ========== Buffer Overflow Tests ========== */

/* Test: strcpy without length check - VULNERABLE */
void process_username(const char* input) {
    char buffer[64];
    strcpy(buffer, input);  /* Dangerous! */
    printf("User: %s\n", buffer);
}

/* Test: strcat without length check - VULNERABLE */
void build_path(const char* dir, const char* file) {
    char path[128];
    strcpy(path, dir);
    strcat(path, "/");
    strcat(path, file);
    printf("Path: %s\n", path);
}

/* Test: sprintf without length check - VULNERABLE */
void format_message(const char* name, int count) {
    char message[100];
    sprintf(message, "User %s has %d items", name, count);
    printf("%s\n", message);
}

/* Test: gets is always dangerous - VULNERABLE */
void read_line_gets(void) {
    char buffer[256];
    gets(buffer);  /* NEVER use gets() */
    printf("Got: %s\n", buffer);
}

/* Test: scanf %s without length - VULNERABLE */
void read_input_scanf(void) {
    char name[32];
    scanf("%s", name);  /* Should use %31s */
    printf("Name: %s\n", name);
}

/* Test: Safe alternative using strncpy */
void process_username_safe(const char* input) {
    char buffer[64];
    strncpy(buffer, input, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\0';
    printf("User: %s\n", buffer);
}

/* ========== Format String Tests ========== */

/* Test: Format string from user input - VULNERABLE */
void log_message(const char* msg) {
    printf(msg);  /* Dangerous if msg contains %n */
}

/* Test: Format string from function parameter - VULNERABLE */
void log_with_format(const char* format) {
    fprintf(stderr, format);
}

/* Test: Safe format string */
void log_message_safe(const char* msg) {
    printf("%s", msg);  /* Safe: format is literal */
}

/* Test: syslog with variable format - VULNERABLE */
void log_to_syslog(const char* user_msg) {
    /* syslog(LOG_INFO, user_msg); */  /* Would be vulnerable */
    printf("Would syslog: %s\n", user_msg);
}

/* ========== TOCTOU Tests ========== */

/* Test: access then open - VULNERABLE */
int open_if_readable(const char* path) {
    if (access(path, R_OK) == 0) {
        /* TOCTOU: file could change between access and open */
        return open(path, O_RDONLY);
    }
    return -1;
}

/* Test: stat then unlink - VULNERABLE */
int delete_if_regular(const char* path) {
    struct stat st;
    if (stat(path, &st) == 0) {
        if (S_ISREG(st.st_mode)) {
            /* TOCTOU: file could be replaced with symlink */
            return unlink(path);
        }
    }
    return -1;
}

/* Test: stat then open - VULNERABLE */
int open_regular_file(const char* path) {
    struct stat st;
    if (stat(path, &st) < 0) {
        return -1;
    }
    if (!S_ISREG(st.st_mode)) {
        return -1;
    }
    /* TOCTOU window here */
    return open(path, O_RDONLY);
}

/* Test: Safe TOCTOU pattern with fstat */
int open_and_verify(const char* path) {
    int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) {
        return -1;
    }
    struct stat st;
    if (fstat(fd, &st) < 0) {
        close(fd);
        return -1;
    }
    if (!S_ISREG(st.st_mode)) {
        close(fd);
        return -1;
    }
    return fd;  /* Safe: fstat on open fd */
}

/* Main for testing */
int main(void) {
    return 0;
}
