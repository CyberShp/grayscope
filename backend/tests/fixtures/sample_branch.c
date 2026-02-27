/**
 * Sample C file for testing branch extraction.
 * Contains if/else, switch/case, and loop constructs.
 */

#include <stdio.h>
#include <stdlib.h>

int global_counter = 0;
static int g_status = 0;

/* Process input data with validation */
int process_input(char *buffer, int size) {
    if (buffer == NULL) {
        return -1;
    }
    
    if (size <= 0) {
        return -2;
    } else if (size > 1024) {
        return -3;
    } else {
        global_counter++;
    }
    
    for (int i = 0; i < size; i++) {
        if (buffer[i] == '\0') {
            break;
        }
    }
    
    return 0;
}

/* Handle command with switch/case */
int handle_command(int cmd) {
    switch (cmd) {
        case 1:
            g_status = 1;
            return process_input(NULL, 0);
        case 2:
            g_status = 2;
            break;
        case 3:
            g_status = 3;
            break;
        default:
            g_status = -1;
            return -1;
    }
    
    while (g_status > 0) {
        g_status--;
    }
    
    return 0;
}

/* Entry point handler */
void cmd_handler(int cmd, char *data, int len) {
    int ret = handle_command(cmd);
    if (ret < 0) {
        return;
    }
    process_input(data, len);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        return 1;
    }
    cmd_handler(1, argv[1], 10);
    return 0;
}
