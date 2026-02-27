/**
 * Sample C file for testing protocol operation extraction.
 * Contains socket operations and protocol state transitions.
 */

#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <pthread.h>

pthread_mutex_t conn_lock;
int g_connection_state = 0;

/* Initialize connection */
int init_connection(const char *host, int port) {
    int sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) {
        return -1;
    }
    
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = port;
    
    if (connect(sockfd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sockfd);
        return -2;
    }
    
    g_connection_state = 1;
    return sockfd;
}

/* Send data with error handling */
int send_data(int fd, const char *input_buffer, int len) {
    pthread_mutex_lock(&conn_lock);
    
    if (fd < 0) {
        // Bug: protocol op in error path without close
        pthread_mutex_unlock(&conn_lock);
        return -1;
    }
    
    int sent = send(fd, input_buffer, len, 0);
    if (sent < 0) {
        // Error branch but no close
        pthread_mutex_unlock(&conn_lock);
        return -2;
    }
    
    pthread_mutex_unlock(&conn_lock);
    return sent;
}

/* Receive with blocking while holding lock */
int recv_data_handler(int fd, char *buffer, int maxlen) {
    pthread_mutex_lock(&conn_lock);
    
    // Bug: blocking recv while holding lock
    int received = recv(fd, buffer, maxlen, 0);
    
    pthread_mutex_unlock(&conn_lock);
    return received;
}

/* Accept connection callback */
int accept_connection_callback(int server_fd) {
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);
    
    pthread_mutex_lock(&conn_lock);
    // Bug: blocking accept while holding lock
    int client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &addr_len);
    pthread_mutex_unlock(&conn_lock);
    
    if (client_fd < 0) {
        return -1;
    }
    
    g_connection_state = 2;
    return client_fd;
}

/* Proper cleanup */
void close_connection(int fd) {
    pthread_mutex_lock(&conn_lock);
    close(fd);
    g_connection_state = 0;
    pthread_mutex_unlock(&conn_lock);
}

/* Process handler entry point */
void process_handler(int fd, int cmd) {
    char buffer[256];
    
    if (cmd == 1) {
        send_data(fd, "hello", 5);
    } else if (cmd == 2) {
        recv_data_handler(fd, buffer, sizeof(buffer));
    } else if (cmd == 0) {
        close_connection(fd);
    }
}
